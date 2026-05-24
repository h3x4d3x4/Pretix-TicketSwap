"""
SecureSwap partner endpoints + Pretix admin views.

Partner endpoints implement the OpenAPI spec at
``https://ticketswap.stoplight.io/docs/secondary-ticketing``. TicketSwap
calls these; the plugin authenticates with a per-organizer Bearer token
and returns spec-shaped JSON.

Admin views surface integration state inside Pretix's control panel.
"""

import json
import logging
from typing import Any, Dict, Optional

from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import FormView, TemplateView
from pretix.base.models import Organizer
from pretix.control.permissions import EventPermissionRequiredMixin

from .auth import (
    EVENT_ENABLED_SETTING,
    PARTNER_TOKEN_SETTING,
    authenticate_partner,
    enabled_events_for,
    is_event_enabled,
)
from .forms import TicketSwapEventForm, TicketSwapOrganizerForm
from .personalization import get_fields_for_event
from .pdf import absolute_pdf_url
from .serializers import (
    event_uuid,
    position_uuid,
    serialize_generic_event,
    serialize_ticket_listing,
    serialize_ticket_type,
    serialize_validation_event,
)
from .ticket_ops import (
    OrderCancelled,
    PersonalizationNotAllowed,
    ResellNotAllowed,
    TicketAlreadyScanned,
    TicketAlreadySwapped,
    TicketOpError,
    apply_personalization,
    assert_swappable,
    find_event_by_uuid,
    find_position_by_barcode,
    find_position_by_revoked_barcode,
    find_position_by_ticket_uuid,
    find_positions_for_unique_identifier,
    lock_position,
    page_events,
    swap_barcode,
    unlock_position,
)
from .utils import ensure_dict

logger = logging.getLogger(__name__)

# Cap on inbound JSON body. Swap/personalize payloads are tiny in practice;
# 64KB is several orders of magnitude over what the spec needs and shields
# the endpoints from accidental DOS.
MAX_BODY_BYTES = 64 * 1024


# ---- Helpers ---------------------------------------------------------------


def _no_store(response):
    """Mark a partner-facing response as non-cacheable.

    Ticket barcodes and PDF URLs are short-lived secrets; we don't want
    a CDN or proxy to retain them past the request that generated them.
    """
    response["Cache-Control"] = "no-store"
    return response


def _json(body, status: int):
    return _no_store(JsonResponse(body, status=status))


def _empty(status: int):
    return _no_store(HttpResponse(status=status))


# Per-error-code flags. The spec is subtle here: `valid` means "the ticket
# is still redeemable at the gate"; `swappable` means "can be resold". A
# free/deposit ticket is still valid at the gate but not eligible for
# resale, hence RESELL_NOT_ALLOWED carries valid=True.
_ERROR_FLAGS = {
    "RESELL_NOT_ALLOWED": (True, False),
    "TICKET_NOT_FOUND": (False, False),
    "TICKET_ALREADY_SWAPPED": (False, False),
    "TICKET_ALREADY_SCANNED": (False, False),
    "ORDER_CANCELLED": (False, False),
    "UNAUTHORIZED": (False, False),
    "PERSONALIZATION_NOT_ALLOWED": (False, False),
}


def _error_response(barcode: str, error_code: str, status: int) -> JsonResponse:
    """Build the spec's ``ErrorResponse`` shape."""
    valid, swappable = _ERROR_FLAGS.get(error_code, (False, False))
    return _json(
        {
            "barcode": barcode or "",
            "valid": valid,
            "swappable": swappable,
            "error": error_code,
        },
        status=status,
    )


def _read_json_body(request) -> Optional[Dict[str, Any]]:
    raw = request.body
    if len(raw) > MAX_BODY_BYTES:
        return None
    try:
        data = json.loads(raw.decode("utf-8")) if raw else {}
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _validate_customer(customer: Any) -> bool:
    """Spec's CustomerBase: firstName, lastName, email, language all required.

    We accept the call even if these are missing, but log a warning so an
    operator can debug a TicketSwap-side regression. A strict reject would
    block resales for a typo on the partner side; that's worse than a
    permissive accept.
    """
    if not isinstance(customer, dict):
        return False
    return all(
        isinstance(customer.get(k), str) and customer.get(k)
        for k in ("firstName", "lastName", "email", "language")
    )


def _int_query(request, name: str, default: int, minimum: int, maximum: int) -> int:
    raw = request.GET.get(name)
    if raw is None or raw == "":
        return default
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, v))


# ---- Partner endpoints -----------------------------------------------------


@method_decorator(csrf_exempt, name="dispatch")
class ValidateView(View):
    """GET /validate?barcode=…

    On success returns ``ValidationResponse``; on business-rule failure
    returns 200 + ``ErrorResponse`` per spec. Only auth failures and
    missing tickets are non-200.
    """

    def get(self, request, organizer):
        organizer_obj, error = authenticate_partner(request, organizer)
        if error is not None:
            return error

        barcode = request.GET.get("barcode", "").strip()
        if not barcode:
            return _error_response("", "TICKET_NOT_FOUND", 404)

        position = find_position_by_barcode(organizer_obj, barcode)
        if position is None:
            # Distinguish "never existed" from "known but already swapped" — the
            # spec's two error codes drive different TicketSwap UX paths.
            if find_position_by_revoked_barcode(organizer_obj, barcode) is not None:
                return _error_response(barcode, "TICKET_ALREADY_SWAPPED", 200)
            return _error_response(barcode, "TICKET_NOT_FOUND", 404)

        try:
            assert_swappable(position)
        except TicketOpError as e:
            return _error_response(barcode, e.error_code, e.http_status)

        pdf_url = absolute_pdf_url(request, position) or None

        return _json({
            "id": position_uuid(position),
            "barcode": position.secret,
            "swappable": True,
            "valid": True,
            "scanned_at": None,
            "pdf": pdf_url,
            "personalization_required": _personalization_required(position.order.event),
            "event": serialize_validation_event(position.order.event),
            "type": serialize_ticket_type(position.item, position),
        }, status=200)


def _personalization_required(event) -> bool:
    return bool(event.settings.get(
        "ticketswap_personalization_required", as_type=bool, default=False
    ))


@method_decorator(csrf_exempt, name="dispatch")
class SwapView(View):
    """POST /swap — cancel old barcode, issue new one + PDF URL."""

    def post(self, request, organizer):
        organizer_obj, error = authenticate_partner(request, organizer)
        if error is not None:
            return error

        data = _read_json_body(request)
        if data is None:
            return _error_response("", "TICKET_NOT_FOUND", 400)

        ticket = data.get("ticket") or {}
        customer = data.get("customer") or {}
        barcode = (ticket.get("barcode") or "").strip()
        if not barcode:
            return _error_response("", "TICKET_NOT_FOUND", 404)

        if not _validate_customer(customer):
            logger.warning(
                "secureswap: /swap received malformed customer payload barcode=%s",
                barcode,
            )

        position = find_position_by_barcode(organizer_obj, barcode)
        if position is None:
            return _error_response(barcode, "TICKET_NOT_FOUND", 404)

        try:
            assert_swappable(position)
        except (TicketAlreadySwapped, TicketAlreadyScanned, OrderCancelled):
            # Swap is a mutating endpoint — spec doesn't list these as 200,
            # so we surface 400 here (different from /validate behavior).
            return _error_response(barcode, "RESELL_NOT_ALLOWED", 400)
        except ResellNotAllowed:
            return _error_response(barcode, "RESELL_NOT_ALLOWED", 400)
        except TicketOpError as e:
            return _error_response(barcode, e.error_code, 400)

        try:
            new_barcode = swap_barcode(position, customer)
        except TicketOpError as e:
            return _error_response(barcode, e.error_code, 400)

        pretix_only_pdf = _personalization_required(position.order.event)
        # Per spec, /swap MAY return pdf:null when /personalize is expected
        # next. We honor that for events that require personalization.
        pdf_url = None if pretix_only_pdf else absolute_pdf_url(request, position)

        body = {
            "id": position_uuid(position),
            "barcode": new_barcode,
            "pdf": pdf_url,
        }
        if pretix_only_pdf:
            body["personalization_required"] = True
        return _json(body, status=201)


@method_decorator(csrf_exempt, name="dispatch")
class PersonalizeView(View):
    """POST /personalize — apply attendee info + regenerate PDF."""

    def post(self, request, organizer):
        organizer_obj, error = authenticate_partner(request, organizer)
        if error is not None:
            return error

        data = _read_json_body(request)
        if data is None:
            return _error_response("", "PERSONALIZATION_NOT_ALLOWED", 400)

        ticket = data.get("ticket") or {}
        customer = data.get("customer") or {}
        barcode = (ticket.get("barcode") or "").strip()
        if not barcode:
            return _error_response("", "TICKET_NOT_FOUND", 404)

        position = find_position_by_barcode(organizer_obj, barcode)
        if position is None:
            return _error_response(barcode, "TICKET_NOT_FOUND", 404)

        # Personalization is permitted only if the event opts into it. If
        # the event doesn't ask for personalization, spec says: discard the
        # data and return success so TicketSwap can still deliver the PDF.
        if not _personalization_required(position.order.event):
            return _json({
                "id": position_uuid(position),
                "barcode": position.secret,
                "pdf": absolute_pdf_url(request, position),
            }, status=200)

        try:
            apply_personalization(position, customer)
        except PersonalizationNotAllowed:
            return _error_response(barcode, "PERSONALIZATION_NOT_ALLOWED", 400)
        except TicketOpError as e:
            return _error_response(barcode, e.error_code, e.http_status)

        return _json({
            "id": position_uuid(position),
            "barcode": position.secret,
            "pdf": absolute_pdf_url(request, position),
        }, status=200)


@method_decorator(csrf_exempt, name="dispatch")
class PersonalizationFieldsView(View):
    """GET /personalization-fields/{barcode}"""

    def get(self, request, organizer, barcode):
        organizer_obj, error = authenticate_partner(request, organizer)
        if error is not None:
            return error

        position = find_position_by_barcode(organizer_obj, barcode)
        if position is None:
            # Spec returns 404 with empty content; we mirror that.
            return _empty(404)

        fields = get_fields_for_event(position.order.event)
        return _no_store(JsonResponse(fields, safe=False, status=200))


@method_decorator(csrf_exempt, name="dispatch")
class EventsListView(View):
    """GET /events?page=N&page_size=M"""

    def get(self, request, organizer):
        organizer_obj, error = authenticate_partner(request, organizer)
        if error is not None:
            return error

        page = _int_query(request, "page", default=1, minimum=1, maximum=10_000)
        page_size = _int_query(request, "page_size", default=20, minimum=1, maximum=200)

        events, total = page_events(organizer_obj, page, page_size)
        total_pages = max(1, (total + page_size - 1) // page_size) if total else 0

        return _json({
            "events": [serialize_generic_event(e) for e in events],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "total_results": total,
            },
        }, status=200)


@method_decorator(csrf_exempt, name="dispatch")
class EventGetView(View):
    """GET /events/{id}"""

    def get(self, request, organizer, id):  # noqa: A002 — matches spec param name
        organizer_obj, error = authenticate_partner(request, organizer)
        if error is not None:
            return error

        event = find_event_by_uuid(organizer_obj, id)
        if event is None:
            return _empty(404)
        return _json(serialize_generic_event(event), status=200)


@method_decorator(csrf_exempt, name="dispatch")
class TicketsListView(View):
    """GET /tickets/{uniqueIdentifier}"""

    def get(self, request, organizer, uniqueIdentifier):  # noqa: N803
        organizer_obj, error = authenticate_partner(request, organizer)
        if error is not None:
            return error

        positions = find_positions_for_unique_identifier(
            organizer_obj, uniqueIdentifier
        )
        if not positions:
            return _json({"error_code": "TICKETS_NOT_FOUND"}, status=404)

        return _json({
            "tickets": [serialize_ticket_listing(p) for p in positions],
        }, status=200)


@method_decorator(csrf_exempt, name="dispatch")
class LockView(View):
    """POST /lock/{ticketId} + DELETE /lock/{ticketId}"""

    def post(self, request, organizer, ticketId):  # noqa: N803
        organizer_obj, error = authenticate_partner(request, organizer)
        if error is not None:
            return error

        position = find_position_by_ticket_uuid(organizer_obj, ticketId)
        if position is None:
            return _empty(404)

        try:
            lock_position(position)
        except OrderCancelled:
            return _json({"error_code": "ORDER_CANCELLED"}, status=409)
        except TicketOpError as e:
            return _json({"error_code": e.error_code}, status=409)
        return _empty(201)

    def delete(self, request, organizer, ticketId):  # noqa: N803
        organizer_obj, error = authenticate_partner(request, organizer)
        if error is not None:
            return error

        position = find_position_by_ticket_uuid(organizer_obj, ticketId)
        if position is None:
            return _empty(404)

        unlock_position(position)
        return _empty(204)


# ---- Admin: dashboard + settings ------------------------------------------


def _build_partner_base_url(request, organizer_slug: str) -> str:
    try:
        path = reverse(
            "plugins:pretix_ticketswap:partner_root",
            kwargs={"organizer": organizer_slug},
        )
    except Exception:
        return ""
    return request.build_absolute_uri(path)


def _stats(event):
    """Cheap per-event counters scanned from positions with ``ticketswap``
    metadata. Bounded by the ``meta_info__contains`` filter so events with
    millions of plain positions stay cheap.
    """
    from pretix.base.models import OrderPosition

    listed = swapped = personalized = locked = 0
    activity = []

    qs = (
        OrderPosition.objects.filter(
            order__event=event,
            meta_info__contains='"ticketswap"',
        )
        .select_related("order")
        .order_by("-order__datetime")
    )

    for pos in qs.iterator(chunk_size=500):
        ts = ensure_dict(pos.meta_info).get("ticketswap", {})
        if ts.get("locked"):
            listed += 1  # spec calls listed-on-TicketSwap "locked" on our side
            locked += 1
        if ts.get("swap_count"):
            swapped += 1
        if ts.get("personalized"):
            personalized += 1

        if len(activity) < 8:
            state = "unknown"
            if ts.get("personalized"):
                state = "personalized"
            elif ts.get("swap_count"):
                state = "swapped"
            elif ts.get("locked"):
                state = "locked"
            activity.append({
                "order_code": pos.order.code,
                "position_id": pos.id,
                "state": state,
                "when": pos.order.datetime,
            })

    return {
        "listed_tickets": listed,
        "secureswap_transfers": swapped,
        "personalized_tickets": personalized,
        "locked_tickets": locked,
    }, activity


class TicketSwapDashboardView(EventPermissionRequiredMixin, TemplateView):
    """Event-level dashboard: state, partner URL, recent activity."""

    template_name = "pretix_ticketswap/dashboard.html"
    permission = "can_view_orders"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        event = self.request.event
        organizer = self.request.organizer

        context["plugin_enabled"] = is_event_enabled(event)
        context["partner_token_configured"] = bool(
            organizer.settings.get(PARTNER_TOKEN_SETTING, as_type=str, default="")
        )
        context["partner_base_url"] = _build_partner_base_url(self.request, organizer.slug)
        context["personalization_required"] = _personalization_required(event)
        context["stats"], context["recent_activity"] = _stats(event)
        context["event_uuid"] = event_uuid(event)
        return context


class TicketSwapEventSettingsView(EventPermissionRequiredMixin, FormView):
    """Per-event settings: enable toggle, personalization, venue overrides."""

    template_name = "pretix_ticketswap/settings.html"
    form_class = TicketSwapEventForm
    permission = "can_change_event_settings"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["event"] = self.request.event
        kwargs["initial"] = self.form_class.initial_from_event(self.request.event)
        return kwargs

    def form_valid(self, form):
        form.save_to_event(self.request.event)
        return redirect(reverse(
            "plugins:pretix_ticketswap:settings",
            kwargs={
                "event": self.request.event.slug,
                "organizer": self.request.organizer.slug,
            },
        ))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        organizer = self.request.organizer
        context["partner_token_configured"] = bool(
            organizer.settings.get(PARTNER_TOKEN_SETTING, as_type=str, default="")
        )
        context["partner_base_url"] = _build_partner_base_url(self.request, organizer.slug)
        context["organizer_settings_hint"] = _(
            "The partner token is shared across all events in this organizer. "
            "Configure it once in the organizer settings."
        )
        return context


class TicketSwapOrganizerSettingsView(FormView):
    """Organizer-level settings: the partner token + base URL display.

    Lives under ``/control/organizer/<organizer>/secureswap/`` so an admin
    with organizer-level permissions can rotate the partner token without
    touching every event.
    """

    template_name = "pretix_ticketswap/organizer_settings.html"
    form_class = TicketSwapOrganizerForm

    def dispatch(self, request, *args, **kwargs):
        from django.http import Http404, HttpResponseForbidden
        try:
            self.organizer = Organizer.objects.get(slug=kwargs["organizer"])
        except Organizer.DoesNotExist:
            raise Http404()
        if not request.user.has_organizer_permission(
            self.organizer, "can_change_organizer_settings", request=request
        ):
            return HttpResponseForbidden()
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["organizer"] = self.organizer
        kwargs["initial"] = self.form_class.initial_from_organizer(self.organizer)
        return kwargs

    def form_valid(self, form):
        form.save_to_organizer(self.organizer)
        return redirect(reverse(
            "plugins:pretix_ticketswap:organizer_settings",
            kwargs={"organizer": self.organizer.slug},
        ))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["organizer"] = self.organizer
        context["partner_base_url"] = _build_partner_base_url(self.request, self.organizer.slug)
        context["enabled_event_count"] = sum(
            1 for e in enabled_events_for(self.organizer) if is_event_enabled(e)
        )
        context["EVENT_ENABLED_SETTING"] = EVENT_ENABLED_SETTING
        return context
