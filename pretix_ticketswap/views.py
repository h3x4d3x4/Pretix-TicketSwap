"""
Django views for the TicketSwap plugin admin interface and webhook.
"""

import hashlib
import json
import logging

from django.contrib import messages
from django.core.cache import cache
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import FormView, TemplateView
from pretix.control.permissions import EventPermissionRequiredMixin

from .forms import TicketSwapSettingsForm
from .ticketswap_api import TicketSwapAPI, TicketSwapAPIError, TicketSwapAuthError
from .utils import dump_meta, ensure_dict

logger = logging.getLogger(__name__)

# 64 KB is well over real webhook sizes and leaves us plenty of headroom
# while shielding the view from memory-exhaustion abuse.
MAX_WEBHOOK_PAYLOAD_SIZE = 65536

# Webhook de-duplication window. Stores recently-seen (event_slug, webhook_id
# or signature hash) tuples so the same delivery cannot be replayed against
# us within this period.
WEBHOOK_REPLAY_TTL = 6 * 60 * 60  # 6h

# TTL for the ticketswap_event_id → Pretix Event.pk reverse lookup cache.
EVENT_LOOKUP_TTL = 6 * 60 * 60  # 6h


def _conn_cache_key(event):
    return f"ticketswap_conn_{event.pk}"


def _event_lookup_cache_key(ticketswap_event_id):
    return f"ticketswap_event_lookup_{ticketswap_event_id}"


def invalidate_event_lookup_cache(ticketswap_event_id):
    if ticketswap_event_id:
        cache.delete(_event_lookup_cache_key(ticketswap_event_id))


def _get_connection_status(event):
    """Cached connection status — 5 min on success, 1 min on failure."""
    api_key = event.settings.get("ticketswap_api_key", as_type=str, default="")
    api_secret = event.settings.get("ticketswap_api_secret", as_type=str, default="")

    if not api_key or not api_secret:
        return "not_configured", True

    cached = cache.get(_conn_cache_key(event))
    if cached is not None:
        return cached["status"], cached["sandbox"]

    try:
        api = TicketSwapAPI(api_key, api_secret)
        status = "connected" if api.test_connection() else "failed"
        sandbox = api.sandbox_mode
        cache.set(_conn_cache_key(event), {"status": status, "sandbox": sandbox}, 300)
        return status, sandbox
    except (TicketSwapAPIError, TicketSwapAuthError):
        cache.set(_conn_cache_key(event), {"status": "failed", "sandbox": True}, 60)
        return "failed", True


def _compute_stats_and_activity(event, activity_limit=8):
    """Stats + most-recent-activity from position meta_info.

    One DB pass (most-recent first) populates both the counters and the
    short activity list shown on the dashboard. Bounded by ``meta_info``
    containing the ``ticketswap`` marker so events with millions of
    plain positions stay cheap.
    """
    from pretix.base.models import OrderPosition

    listed = sold = transferred = 0
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
        if ts.get("listed"):
            listed += 1
        if ts.get("sold"):
            sold += 1
        if ts.get("transferred"):
            transferred += 1

        if len(activity) < activity_limit:
            state = "unknown"
            if ts.get("transferred"):
                state = "transferred"
            elif ts.get("sold"):
                state = "sold"
            elif ts.get("cancelled"):
                state = "cancelled"
            elif ts.get("listed"):
                state = "listed"
            elif ts.get("synced"):
                state = "synced"
            activity.append({
                "order_code": pos.order.code,
                "position_id": pos.id,
                "ticket_id": ts.get("ticket_id"),
                "state": state,
                "when": pos.order.datetime,
            })

    stats = {
        "listed_tickets": listed,
        "sold_tickets": sold,
        "secureswap_transfers": transferred,
    }
    return stats, activity


def _build_webhook_url(request):
    """Absolute URL of the webhook endpoint, for the admin to paste
    into the TicketSwap partnership dashboard."""
    try:
        return request.build_absolute_uri(
            reverse("plugins:pretix_ticketswap:webhook")
        )
    except Exception:
        return ""


class TicketSwapDashboardView(EventPermissionRequiredMixin, TemplateView):
    """Dashboard: connection status, sync state, and statistics."""

    template_name = "pretix_ticketswap/dashboard.html"
    permission = "can_view_orders"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        event = self.request.event

        context["connection_status"], context["sandbox_mode"] = _get_connection_status(event)
        context["ticketswap_event_id"] = event.settings.get(
            "ticketswap_event_id", as_type=str, default=""
        )
        context["stats"], context["recent_activity"] = _compute_stats_and_activity(event)
        context["plugin_enabled"] = event.settings.get(
            "ticketswap_enabled", as_type=bool, default=False
        )
        context["auto_enable_resale"] = event.settings.get(
            "ticketswap_auto_enable_resale", as_type=bool, default=True
        )
        context["webhook_secret_configured"] = bool(
            event.settings.get("ticketswap_webhook_secret", as_type=str, default="")
        )
        context["webhook_url"] = _build_webhook_url(self.request)
        return context


class TicketSwapTestConnectionView(EventPermissionRequiredMixin, View):
    """AJAX endpoint to validate credentials from the settings form."""

    permission = "can_change_event_settings"

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse(
                {"success": False, "message": str(_("Invalid request"))},
                status=400,
            )

        api_key = data.get("api_key")
        api_secret = data.get("api_secret")

        # Allow testing with the stored secret if the password field is blank
        if api_key and not api_secret:
            api_secret = request.event.settings.get(
                "ticketswap_api_secret", as_type=str, default=""
            )

        if not api_key or not api_secret:
            return JsonResponse({
                "success": False,
                "message": str(_("API key and secret are required")),
            })

        try:
            api = TicketSwapAPI(api_key=api_key, api_secret=api_secret)
            if api.test_connection():
                cache.delete(_conn_cache_key(request.event))
                return JsonResponse({
                    "success": True,
                    "message": str(_("Connection successful! API credentials are valid.")),
                })
            return JsonResponse({
                "success": False,
                "message": str(_("Connection failed. Please check your credentials.")),
            })
        except TicketSwapAuthError:
            return JsonResponse({
                "success": False,
                "message": str(_("Invalid API credentials")),
            })
        except Exception:
            logger.exception("ticketswap: connection test error")
            return JsonResponse({
                "success": False,
                "message": str(_(
                    "Connection test failed. Please verify your credentials and try again."
                )),
            })


def _resolve_event_for_webhook(ticketswap_event_id):
    """Find the Pretix Event whose settings map to ``ticketswap_event_id``.

    Results are cached for ``EVENT_LOOKUP_TTL`` so the webhook path is
    O(1) on repeat deliveries. A negative cache (``None``) is stored
    briefly so a flood of bad event_ids doesn't repeatedly hit the DB.
    """
    from pretix.base.models import Event

    cache_key = _event_lookup_cache_key(ticketswap_event_id)
    cached = cache.get(cache_key)
    if cached is not None:
        if cached == "__MISS__":
            return None
        try:
            return Event.objects.select_related("organizer").get(pk=cached)
        except Event.DoesNotExist:
            cache.delete(cache_key)

    for candidate in Event.objects.filter(
        plugins__contains="pretix_ticketswap"
    ).select_related("organizer"):
        stored_id = candidate.settings.get(
            "ticketswap_event_id", as_type=str, default=""
        )
        if stored_id == ticketswap_event_id:
            cache.set(cache_key, candidate.pk, EVENT_LOOKUP_TTL)
            return candidate

    cache.set(cache_key, "__MISS__", 60)
    return None


def _find_position_by_ticket_id(event, ticket_id):
    """DB-filter lookup for a position whose meta_info stores ``ticket_id``."""
    from pretix.base.models import OrderPosition

    # The substring is unique enough to narrow candidates at the DB level.
    marker = json.dumps({"ticket_id": ticket_id})[1:-1]  # drops the outer braces
    qs = OrderPosition.objects.filter(
        order__event=event,
        meta_info__contains=marker,
    ).select_related("order")
    for position in qs.iterator(chunk_size=50):
        meta = ensure_dict(position.meta_info)
        if meta.get("ticketswap", {}).get("ticket_id") == ticket_id:
            return position, meta
    return None, None


class TicketSwapWebhookView(View):
    """Webhook endpoint for TicketSwap notifications."""

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        raw_body = request.body
        if len(raw_body) > MAX_WEBHOOK_PAYLOAD_SIZE:
            return JsonResponse({"error": "Payload too large"}, status=413)

        try:
            data = json.loads(raw_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        event_type = data.get("event")
        ticketswap_event_id = data.get("event_id")
        if not ticketswap_event_id or not isinstance(ticketswap_event_id, str):
            logger.warning("ticketswap: webhook missing event_id")
            return JsonResponse({"error": "Missing event_id"}, status=400)

        try:
            event = _resolve_event_for_webhook(ticketswap_event_id)
        except Exception:
            logger.exception("ticketswap: error resolving event for webhook")
            return JsonResponse({"error": "Internal server error"}, status=500)

        if event is None:
            logger.warning(
                "ticketswap: unknown ticketswap_event_id=%s", ticketswap_event_id
            )
            return JsonResponse({"error": "Unknown event"}, status=404)

        signature = request.META.get("HTTP_X_TICKETSWAP_SIGNATURE", "")
        webhook_secret = event.settings.get(
            "ticketswap_webhook_secret", as_type=str, default=""
        )
        if not webhook_secret:
            logger.error(
                "ticketswap: webhook secret not configured for event=%s", event.slug
            )
            return JsonResponse({"error": "Webhook not configured"}, status=500)

        api = TicketSwapAPI()
        if not api.verify_webhook_signature(raw_body, signature, webhook_secret):
            logger.warning(
                "ticketswap: invalid webhook signature event=%s", event.slug
            )
            return JsonResponse({"error": "Invalid signature"}, status=401)

        # Replay protection: if we've seen this exact (event, webhook id or
        # signature) before, respond 200 without re-running the handler.
        replay_id = (
            data.get("id")
            or data.get("webhook_id")
            or hashlib.sha256(raw_body).hexdigest()
        )
        replay_key = f"ticketswap_seen_{event.pk}_{replay_id}"
        if cache.get(replay_key):
            logger.info(
                "ticketswap: duplicate webhook ignored event=%s replay_id=%s",
                event.slug, replay_id,
            )
            return JsonResponse({"status": "ok", "duplicate": True})
        cache.set(replay_key, True, WEBHOOK_REPLAY_TTL)

        logger.info(
            "ticketswap: webhook received event=%s type=%s id=%s",
            event.slug, event_type, replay_id,
        )

        try:
            if event_type == "ticket.sold":
                self._handle_ticket_sold(event, data)
            elif event_type == "ticket.transferred":
                self._handle_ticket_transferred(event, data)
            elif event_type == "ticket.cancelled":
                self._handle_ticket_cancelled(event, data)
            else:
                logger.warning(
                    "ticketswap: unknown event type event=%s type=%s",
                    event.slug, event_type,
                )
            return JsonResponse({"status": "ok"})
        except Exception:
            logger.exception(
                "ticketswap: webhook processing error event=%s type=%s",
                event.slug, event_type,
            )
            return JsonResponse({"error": "Internal server error"}, status=500)

    def _handle_ticket_sold(self, event, data):
        ticket_id = data.get("ticket_id")
        if not ticket_id:
            return
        position, meta = _find_position_by_ticket_id(event, ticket_id)
        if not position:
            logger.warning(
                "ticketswap: ticket.sold for unknown ticket event=%s ticket=%s",
                event.slug, ticket_id,
            )
            return
        meta["ticketswap"]["sold"] = True
        meta["ticketswap"]["sold_at"] = data.get("sold_at")
        meta["ticketswap"]["listed"] = False
        position.meta_info = dump_meta(meta)
        position.save(update_fields=["meta_info"])
        logger.info(
            "ticketswap: marked position sold event=%s pos=%s ticket=%s",
            event.slug, position.id, ticket_id,
        )

    def _handle_ticket_transferred(self, event, data):
        """SecureSwap: invalidate old barcode, install the new one."""
        old_ticket_id = data.get("old_ticket_id")
        new_ticket_id = data.get("new_ticket_id")
        new_barcode = data.get("new_barcode")

        if not old_ticket_id or not new_barcode:
            logger.error(
                "ticketswap: SecureSwap missing required fields event=%s", event.slug
            )
            return

        position, meta = _find_position_by_ticket_id(event, old_ticket_id)
        if not position:
            logger.warning(
                "ticketswap: SecureSwap for unknown ticket event=%s old_ticket=%s",
                event.slug, old_ticket_id,
            )
            return

        position.secret = new_barcode
        meta["ticketswap"]["ticket_id"] = new_ticket_id
        meta["ticketswap"]["transferred"] = True
        meta["ticketswap"]["old_ticket_id"] = old_ticket_id
        position.meta_info = dump_meta(meta)
        position.save(update_fields=["secret", "meta_info"])
        logger.info(
            "ticketswap: SecureSwap applied event=%s pos=%s old=%s new=%s",
            event.slug, position.id, old_ticket_id, new_ticket_id,
        )

    def _handle_ticket_cancelled(self, event, data):
        ticket_id = data.get("ticket_id")
        if not ticket_id:
            return
        position, meta = _find_position_by_ticket_id(event, ticket_id)
        if not position:
            logger.warning(
                "ticketswap: ticket.cancelled for unknown ticket event=%s ticket=%s",
                event.slug, ticket_id,
            )
            return
        meta["ticketswap"]["listed"] = False
        meta["ticketswap"]["cancelled"] = True
        position.meta_info = dump_meta(meta)
        position.save(update_fields=["meta_info"])
        logger.info(
            "ticketswap: marked listing cancelled event=%s pos=%s ticket=%s",
            event.slug, position.id, ticket_id,
        )


class TicketSwapSettingsView(EventPermissionRequiredMixin, FormView):
    """Event-level configuration for the TicketSwap integration."""

    template_name = "pretix_ticketswap/settings.html"
    form_class = TicketSwapSettingsForm
    permission = "can_change_event_settings"

    _secret_fields = {"ticketswap_api_secret", "ticketswap_webhook_secret"}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["event"] = self.request.event
        kwargs["initial"] = {
            "ticketswap_enabled": self.request.event.settings.get(
                "ticketswap_enabled", as_type=bool, default=False
            ),
            "ticketswap_api_key": self.request.event.settings.get(
                "ticketswap_api_key", as_type=str, default=""
            ),
            # Password fields intentionally left blank — they preserve the stored value.
            "ticketswap_auto_enable_resale": self.request.event.settings.get(
                "ticketswap_auto_enable_resale", as_type=bool, default=True
            ),
            "ticketswap_max_resale_price_percent": self.request.event.settings.get(
                "ticketswap_max_resale_price_percent", as_type=int, default=120
            ),
        }
        return kwargs

    def form_valid(self, form):
        old_ticketswap_event_id = self.request.event.settings.get(
            "ticketswap_event_id", as_type=str, default=""
        )

        for key, value in form.cleaned_data.items():
            if key in self._secret_fields and not value:
                continue
            self.request.event.settings.set(key, value)

        cache.delete(_conn_cache_key(self.request.event))
        invalidate_event_lookup_cache(old_ticketswap_event_id)

        if form.cleaned_data.get("ticketswap_enabled"):
            api_key = (
                form.cleaned_data.get("ticketswap_api_key")
                or self.request.event.settings.get(
                    "ticketswap_api_key", as_type=str, default=""
                )
            )
            api_secret = (
                form.cleaned_data.get("ticketswap_api_secret")
                or self.request.event.settings.get(
                    "ticketswap_api_secret", as_type=str, default=""
                )
            )

            from .tasks import ensure_ticketswap_event

            try:
                api = TicketSwapAPI(api_key, api_secret)
                new_id = ensure_ticketswap_event(self.request.event, api=api)
                if new_id and new_id != old_ticketswap_event_id:
                    invalidate_event_lookup_cache(old_ticketswap_event_id)
                    messages.success(
                        self.request,
                        _(
                            "TicketSwap integration enabled and event created successfully! "
                            "Event ID: {event_id}"
                        ).format(event_id=new_id),
                    )
                else:
                    messages.success(
                        self.request,
                        _("TicketSwap settings saved successfully!"),
                    )
            except TicketSwapAPIError as e:
                logger.error(
                    "ticketswap: settings save — event creation failed event=%s err=%s",
                    self.request.event.slug, e,
                )
                messages.warning(
                    self.request,
                    _(
                        "Settings saved, but failed to create event on TicketSwap. "
                        "You may need to create it manually."
                    ),
                )
        else:
            messages.success(
                self.request,
                _("TicketSwap settings saved successfully!"),
            )

        return redirect(
            reverse(
                "plugins:pretix_ticketswap:settings",
                kwargs={
                    "event": self.request.event.slug,
                    "organizer": self.request.organizer.slug,
                },
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        event = self.request.event
        context["connection_status"], context["sandbox_mode"] = _get_connection_status(event)
        context["ticketswap_event_id"] = event.settings.get(
            "ticketswap_event_id", as_type=str, default=""
        )
        context["api_secret_stored"] = bool(
            event.settings.get("ticketswap_api_secret", as_type=str, default="")
        )
        context["webhook_secret_stored"] = bool(
            event.settings.get("ticketswap_webhook_secret", as_type=str, default="")
        )
        context["webhook_url"] = _build_webhook_url(self.request)
        return context


class TicketSwapOrderActionView(EventPermissionRequiredMixin, View):
    """Admin-initiated manual actions for a single order.

    Lets an operator re-run sync/list/delist after credential or API
    issues are resolved, without waiting for a new signal firing.
    """

    permission = "can_change_orders"

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action") or ""
        order_code = request.POST.get("order") or ""
        if not order_code:
            return JsonResponse({"success": False, "message": "Missing order"}, status=400)

        from pretix.base.models import Order
        try:
            order = Order.objects.get(event=request.event, code=order_code)
        except Order.DoesNotExist:
            raise Http404

        from .tasks import (
            delist_tickets_for_order,
            list_tickets_for_order,
            sync_order_to_ticketswap,
        )

        if action == "sync":
            sync_order_to_ticketswap(request.event.pk, order.pk)
        elif action == "list":
            list_tickets_for_order(request.event.pk, order.pk)
        elif action == "delist":
            delist_tickets_for_order(request.event.pk, order.pk)
        else:
            return JsonResponse(
                {"success": False, "message": f"Unknown action: {action}"},
                status=400,
            )

        logger.info(
            "ticketswap: manual action=%s event=%s order=%s user=%s",
            action, request.event.slug, order.code,
            getattr(request.user, "email", "?"),
        )
        return JsonResponse({"success": True})
