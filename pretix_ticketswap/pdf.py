"""
PDF generation + signed-URL streaming for SecureSwap.

Pretix already renders ticket PDFs via its plugin framework
(``pretix.base.ticketoutput.BaseTicketOutput``). We reuse whichever PDF
output the event has configured, sign a short-lived token for the
position, and expose ``/_secureswap/pdf/<token>`` so TicketSwap can
hand the URL straight to the buyer.
"""

import logging
from typing import Optional, Tuple

from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.http import Http404, HttpResponse
from django.urls import reverse
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)

# 24h gives the buyer a comfortable window to re-download the PDF after
# /swap, while keeping the URL short-lived enough that a leaked link
# doesn't grant indefinite access.
PDF_TOKEN_MAX_AGE = 24 * 60 * 60
_SIGNER_SALT = "pretix_ticketswap.pdf"


def _signer() -> TimestampSigner:
    return TimestampSigner(salt=_SIGNER_SALT)


def signed_token_for_position(position) -> str:
    return _signer().sign(str(position.pk))


def absolute_pdf_url(request, position) -> str:
    """Build an absolute URL TicketSwap can hand to the buyer.

    Returns an empty string if URL reversing fails (the plugin's URLs
    aren't registered — only happens in pathological test setups).
    """
    token = signed_token_for_position(position)
    try:
        path = reverse("plugins:pretix_ticketswap:pdf", kwargs={"token": token})
    except Exception:
        logger.exception("secureswap: failed to reverse pdf URL")
        return ""
    return request.build_absolute_uri(path) if request is not None else path


def _resolve_position_from_token(token: str):
    from pretix.base.models import OrderPosition
    try:
        position_pk_str = _signer().unsign(token, max_age=PDF_TOKEN_MAX_AGE)
    except SignatureExpired:
        raise Http404("Link expired")
    except BadSignature:
        raise Http404("Invalid token")
    try:
        return OrderPosition.objects.select_related(
            "order", "order__event", "item"
        ).get(pk=int(position_pk_str))
    except (OrderPosition.DoesNotExist, ValueError):
        raise Http404("Ticket not found")


def _select_pdf_provider(event):
    """Return the event's PDF ticket output provider, if any.

    Pretix providers are registered via the ``register_ticket_outputs``
    EventPluginSignal — each receiver returns a provider class which we
    instantiate with the event. We pick the first whose ``identifier``
    is ``"pdf"`` (which is what ``pretix.plugins.ticketoutputpdf`` uses).
    Falls back to the first available provider so SecureSwap still works
    with custom ticket outputs.
    """
    from pretix.base.signals import register_ticket_outputs
    try:
        responses = register_ticket_outputs.send(event)
    except Exception:
        logger.exception(
            "secureswap: register_ticket_outputs failed event=%s", event.slug
        )
        return None

    providers = []
    for _receiver, response in responses:
        try:
            providers.append(response(event))
        except Exception:
            logger.exception(
                "secureswap: ticket provider init failed event=%s", event.slug
            )
            continue

    for provider in providers:
        if getattr(provider, "identifier", "").lower() == "pdf":
            return provider
    return providers[0] if providers else None


def render_pdf_for_position(position) -> Optional[Tuple[str, str, bytes]]:
    """Render the ticket via the event's configured ticket output.

    Returns ``(filename, mimetype, content_bytes)`` or ``None`` if no PDF
    provider is available.
    """
    provider = _select_pdf_provider(position.order.event)
    if provider is None:
        logger.warning(
            "secureswap: no PDF provider for event=%s — returning null PDF URL",
            position.order.event.slug,
        )
        return None
    try:
        result = provider.generate(position)
    except Exception:
        logger.exception(
            "secureswap: PDF generation failed pos=%s event=%s",
            position.pk, position.order.event.slug,
        )
        return None
    if not result or len(result) != 3:
        return None
    return result


@require_GET
def pdf_stream_view(request, token: str):
    """Serve the freshly-rendered ticket PDF for a signed token.

    Re-renders on every fetch so a swapped or personalized ticket always
    reflects current state without us having to manage cache eviction.
    """
    position = _resolve_position_from_token(token)
    result = render_pdf_for_position(position)
    if result is None:
        raise Http404("Ticket cannot be rendered")
    filename, mimetype, content = result
    response = HttpResponse(content, content_type=mimetype or "application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    # Don't let CDNs cache the URL — the token can be replayed within its
    # max-age window, but the content reflects live state.
    response["Cache-Control"] = "private, no-store"
    return response
