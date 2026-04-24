"""
TicketSwap API task functions.

Called by signal handlers (scheduled via ``transaction.on_commit``) and
by the manual admin actions in ``views.py``. Kept framework-light so
they can be wrapped with ``@shared_task`` once a Celery broker is
available without touching the call sites.
"""

import logging

from django.db import transaction

from .ticketswap_api import TicketSwapAPI, TicketSwapAPIError
from .utils import dump_meta, ensure_dict

logger = logging.getLogger(__name__)


def _get_api_client(event):
    """Build an API client from event settings, or ``None`` if not configured.

    We intentionally require BOTH key and secret to exit sandbox mode;
    a half-configured event is treated as misconfigured rather than
    silently hitting the sandbox.
    """
    api_key = event.settings.get("ticketswap_api_key", as_type=str, default="")
    api_secret = event.settings.get("ticketswap_api_secret", as_type=str, default="")
    if not api_key or not api_secret:
        return None
    return TicketSwapAPI(api_key, api_secret)


def _build_event_payload(event):
    return {
        "name": str(event.name),
        "date": event.date_from.isoformat() if event.date_from else None,
        "location": str(event.location) if event.location else None,
        "currency": event.currency,
        "slug": event.slug,
    }


def ensure_ticketswap_event(event, api=None):
    """Return the TicketSwap event ID for ``event``, creating it if needed.

    Uses ``SELECT ... FOR UPDATE`` on the Event row to serialise concurrent
    creation attempts so we never double-create on the TicketSwap side.
    """
    from pretix.base.models import Event

    existing = event.settings.get("ticketswap_event_id", as_type=str, default="")
    if existing:
        return existing

    api = api or _get_api_client(event)
    if not api:
        return ""

    with transaction.atomic():
        # Lock the Event row; a second worker will block here and then see the
        # committed setting on its re-read instead of calling the API again.
        Event.objects.select_for_update().filter(pk=event.pk).first()
        existing = event.settings.get("ticketswap_event_id", as_type=str, default="")
        if existing:
            return existing

        result = api.create_event(_build_event_payload(event))
        ticketswap_event_id = result.get("id", "")
        if ticketswap_event_id:
            event.settings.set("ticketswap_event_id", ticketswap_event_id)
        logger.info(
            "ticketswap: event created event=%s ticketswap_event=%s",
            event.slug, ticketswap_event_id,
        )
        return ticketswap_event_id


def sync_order_to_ticketswap(event_pk, order_pk):
    """Sync an order to TicketSwap after placement.

    Creates the TicketSwap event if not already created, then stamps the
    order's meta_info so downstream tasks can look it up.
    """
    from pretix.base.models import Event, Order

    try:
        event = Event.objects.get(pk=event_pk)
        order = Order.objects.get(pk=order_pk)
    except (Event.DoesNotExist, Order.DoesNotExist):
        logger.error(
            "ticketswap: sync_order_to_ticketswap missing event=%s order=%s",
            event_pk, order_pk,
        )
        return

    api = _get_api_client(event)
    if not api:
        logger.warning(
            "ticketswap: credentials missing, skipping sync event=%s order=%s",
            event.slug, order.code,
        )
        return

    try:
        ticketswap_event_id = ensure_ticketswap_event(event, api=api)
        if not ticketswap_event_id:
            logger.warning(
                "ticketswap: event creation returned no id event=%s order=%s",
                event.slug, order.code,
            )
            return

        meta = ensure_dict(order.meta_info)
        ts = meta.setdefault("ticketswap", {})
        ts["event_id"] = ticketswap_event_id
        ts["synced"] = True
        order.meta_info = dump_meta(meta)
        order.save(update_fields=["meta_info"])
        logger.info(
            "ticketswap: order synced event=%s order=%s ticketswap_event=%s",
            event.slug, order.code, ticketswap_event_id,
        )

    except TicketSwapAPIError as e:
        logger.error(
            "ticketswap: failed to sync event=%s order=%s err=%s",
            event.slug, order.code, e,
        )


def _resaleable_positions(order):
    """Positions that are actual (non-canceled, non-addon) tickets."""
    return order.positions.filter(canceled=False, addon_to__isnull=True)


def _build_ticket_payload(event, order, position, ticketswap_event_id):
    max_percent = event.settings.get(
        "ticketswap_max_resale_price_percent", as_type=int, default=120
    )
    try:
        original = float(position.price or 0)
    except (TypeError, ValueError):
        original = 0.0
    max_price = round(original * (max_percent / 100.0), 2) if original else None

    # Attendee info is optional on Pretix orders; try both the position
    # and the invoice address without forcing either to exist.
    attendee_name = (
        getattr(position, "attendee_name_cached", None)
        or getattr(position, "attendee_name", None)
    )
    attendee_email = getattr(position, "attendee_email", None)
    if not attendee_email:
        ia = getattr(order, "invoice_address", None)
        if ia and getattr(ia, "name_cached", None):
            attendee_name = attendee_name or ia.name_cached
        attendee_email = order.email

    return {
        "event_id": ticketswap_event_id,
        "order_code": order.code,
        "position_id": position.id,
        "barcode": position.secret,
        "price": float(position.price or 0),
        "currency": event.currency,
        "max_resale_price": max_price,
        "max_resale_price_percent": max_percent,
        "attendee_name": attendee_name,
        "attendee_email": attendee_email,
        "item": str(position.item.name) if getattr(position, "item", None) else None,
        "variation": (
            str(position.variation.value)
            if getattr(position, "variation", None) else None
        ),
    }


def list_tickets_for_order(event_pk, order_pk):
    """List all resale-eligible tickets in an order.

    Idempotent: positions already marked ``listed`` are skipped. API errors
    on one position do not affect others (per-position isolation).
    """
    from pretix.base.models import Event, Order

    try:
        event = Event.objects.get(pk=event_pk)
        order = Order.objects.get(pk=order_pk)
    except (Event.DoesNotExist, Order.DoesNotExist):
        logger.error(
            "ticketswap: list_tickets_for_order missing event=%s order=%s",
            event_pk, order_pk,
        )
        return

    api = _get_api_client(event)
    if not api:
        return

    ticketswap_event_id = ensure_ticketswap_event(event, api=api)
    if not ticketswap_event_id:
        logger.warning(
            "ticketswap: no ticketswap event id event=%s order=%s",
            event.slug, order.code,
        )
        return

    for position in _resaleable_positions(order).select_related("item", "variation"):
        meta = ensure_dict(position.meta_info)
        if meta.get("ticketswap", {}).get("listed"):
            logger.debug(
                "ticketswap: position already listed event=%s order=%s pos=%s",
                event.slug, order.code, position.id,
            )
            continue

        try:
            payload = _build_ticket_payload(event, order, position, ticketswap_event_id)
            result = api.list_ticket(payload)

            ts = meta.setdefault("ticketswap", {})
            ts["ticket_id"] = result.get("id")
            ts["listed"] = True
            ts["listed_at"] = result.get("created_at")
            position.meta_info = dump_meta(meta)
            position.save(update_fields=["meta_info"])

            logger.info(
                "ticketswap: listed event=%s order=%s pos=%s ticket=%s",
                event.slug, order.code, position.id, result.get("id"),
            )
        except TicketSwapAPIError as e:
            logger.error(
                "ticketswap: listing failed event=%s order=%s pos=%s err=%s",
                event.slug, order.code, position.id, e,
            )


def delist_tickets_for_order(event_pk, order_pk):
    """Delist every position of an order that was previously listed."""
    from pretix.base.models import Event, Order

    try:
        event = Event.objects.get(pk=event_pk)
        order = Order.objects.get(pk=order_pk)
    except (Event.DoesNotExist, Order.DoesNotExist):
        logger.error(
            "ticketswap: delist_tickets_for_order missing event=%s order=%s",
            event_pk, order_pk,
        )
        return

    api = _get_api_client(event)
    if not api:
        return

    for position in order.positions.all():
        meta = ensure_dict(position.meta_info)
        ts = meta.get("ticketswap", {})
        ticket_id = ts.get("ticket_id")

        if not (ticket_id and ts.get("listed")):
            continue

        try:
            api.delist_ticket(ticket_id)
            meta["ticketswap"]["listed"] = False
            meta["ticketswap"]["delisted_at_event"] = True
            position.meta_info = dump_meta(meta)
            position.save(update_fields=["meta_info"])
            logger.info(
                "ticketswap: delisted event=%s order=%s pos=%s ticket=%s",
                event.slug, order.code, position.id, ticket_id,
            )
        except TicketSwapAPIError as e:
            logger.error(
                "ticketswap: delisting failed event=%s order=%s pos=%s err=%s",
                event.slug, order.code, position.id, e,
            )
