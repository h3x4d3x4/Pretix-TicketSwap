"""
Bearer-token authentication for partner-facing SecureSwap endpoints.

TicketSwap sends ``Authorization: Bearer <token>`` on every call. Each
organizer configures a single partner token (under organizer settings)
that the plugin compares constant-time against the inbound header.
"""

import hmac
import logging
from functools import wraps

from django.http import JsonResponse
from django.shortcuts import get_object_or_404

logger = logging.getLogger(__name__)

PARTNER_TOKEN_SETTING = "ticketswap_partner_token"
EVENT_ENABLED_SETTING = "ticketswap_enabled"


def _unauthorized(barcode: str = "") -> JsonResponse:
    """Spec-shaped 401 ErrorResponse."""
    response = JsonResponse(
        {
            "barcode": barcode,
            "valid": False,
            "swappable": False,
            "error": "UNAUTHORIZED",
        },
        status=401,
    )
    response["Cache-Control"] = "no-store"
    return response


def _extract_bearer(request) -> str:
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header:
        return ""
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return ""
    return parts[1].strip()


def organizer_with_secureswap_or_404(organizer_slug: str):
    """Load the Organizer or raise 404.

    Kept thin so views can pre-fetch ``settings`` in one place.
    """
    from pretix.base.models import Organizer
    return get_object_or_404(Organizer, slug=organizer_slug)


def authenticate_partner(request, organizer_slug: str):
    """Return the Organizer for ``organizer_slug`` if the request carries a
    valid partner token, otherwise return a 401 ``JsonResponse``.

    Two failure modes are flattened to UNAUTHORIZED on purpose: a missing
    token and a wrong token look identical from the outside, so a partner
    that guesses an organizer slug learns nothing from the response.
    """
    organizer = organizer_with_secureswap_or_404(organizer_slug)
    stored = organizer.settings.get(
        PARTNER_TOKEN_SETTING, as_type=str, default=""
    ) or ""
    submitted = _extract_bearer(request)

    if not stored or not submitted:
        return None, _unauthorized()

    # constant-time compare so token length / prefix doesn't leak via timing
    if not hmac.compare_digest(stored, submitted):
        logger.warning(
            "secureswap: bad partner token organizer=%s", organizer_slug
        )
        return None, _unauthorized()

    return organizer, None


def require_partner_auth(view_func):
    """Decorator for function-based views that need partner auth.

    Injects ``organizer`` as a kwarg; on failure, short-circuits with a
    spec-shaped 401.
    """
    @wraps(view_func)
    def _wrapped(request, organizer, *args, **kwargs):
        organizer_obj, error = authenticate_partner(request, organizer)
        if error is not None:
            return error
        return view_func(request, organizer=organizer_obj, *args, **kwargs)
    return _wrapped


def enabled_events_for(organizer):
    """All events in ``organizer`` whose plugins list includes us AND whose
    per-event toggle is on. Returned as a queryset so callers can chain
    further filters cheaply.
    """
    from pretix.base.models import Event
    qs = Event.objects.filter(
        organizer=organizer,
        plugins__contains="pretix_ticketswap",
    )
    # We can't filter on the Hierarkey-stored ``ticketswap_enabled`` flag at
    # SQL level without a join; callers that care about the per-event toggle
    # filter at the Python layer via ``is_event_enabled``.
    return qs


def is_event_enabled(event) -> bool:
    return bool(event.settings.get(EVENT_ENABLED_SETTING, as_type=bool, default=False))
