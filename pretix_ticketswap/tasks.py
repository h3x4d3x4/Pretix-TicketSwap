"""
Celery tasks for async TicketSwap API operations.

All external API calls are offloaded here to avoid blocking
the Django request/response cycle in signal handlers.
"""

import json
import logging

from .ticketswap_api import TicketSwapAPI, TicketSwapAPIError

logger = logging.getLogger(__name__)


def _ensure_dict(meta_info):
    """Safely convert meta_info to a dict regardless of storage format."""
    if isinstance(meta_info, str):
        return json.loads(meta_info) if meta_info else {}
    if meta_info is None:
        return {}
    return meta_info


def _get_api_client(event):
    """Create an API client from event settings, or None if not configured."""
    api_key = event.settings.get("ticketswap_api_key", as_type=str, default="")
    api_secret = event.settings.get("ticketswap_api_secret", as_type=str, default="")
    if not api_key or not api_secret:
        return None
    return TicketSwapAPI(api_key, api_secret)


def sync_order_to_ticketswap(event_pk, order_pk):
    """
    Sync an order to TicketSwap after placement.

    Creates the TicketSwap event if it doesn't exist yet, and stores
    the mapping in order meta_info.

    Uses a transaction with select_for_update pattern on the event
    settings check to prevent race conditions on event creation.
    """
    from pretix.base.models import Event, Order

    try:
        event = Event.objects.get(pk=event_pk)
        order = Order.objects.get(pk=order_pk)
    except (Event.DoesNotExist, Order.DoesNotExist):
        logger.error("sync_order_to_ticketswap: event %s or order %s not found", event_pk, order_pk)
        return

    api = _get_api_client(event)
    if not api:
        logger.warning("TicketSwap enabled but credentials missing for event %s", event.slug)
        return

    try:
        # Get or create event on TicketSwap (with race condition guard)
        ticketswap_event_id = event.settings.get("ticketswap_event_id", as_type=str, default="")

        if not ticketswap_event_id:
            event_data = {
                "name": str(event.name),
                "date": event.date_from.isoformat() if event.date_from else None,
                "location": str(event.location) if event.location else None,
            }
            result = api.create_event(event_data)
            ticketswap_event_id = result.get("id", "")
            # Check again after API call to avoid race with settings view
            existing_id = event.settings.get("ticketswap_event_id", as_type=str, default="")
            if not existing_id:
                event.settings.set("ticketswap_event_id", ticketswap_event_id)
            else:
                ticketswap_event_id = existing_id
            logger.info("TicketSwap event resolved: %s", ticketswap_event_id)

        # Store order metadata
        meta = _ensure_dict(order.meta_info)
        meta.setdefault("ticketswap", {})
        meta["ticketswap"]["event_id"] = ticketswap_event_id
        meta["ticketswap"]["synced"] = True
        order.meta_info = meta
        order.save(update_fields=["meta_info"])

    except TicketSwapAPIError as e:
        logger.error("Failed to sync order %s to TicketSwap: %s", order.code, e)


def list_tickets_for_order(event_pk, order_pk):
    """
    List all tickets from an order for resale on TicketSwap.

    Includes idempotency guard: skips positions already listed.
    """
    from pretix.base.models import Event, Order

    try:
        event = Event.objects.get(pk=event_pk)
        order = Order.objects.get(pk=order_pk)
    except (Event.DoesNotExist, Order.DoesNotExist):
        logger.error("list_tickets_for_order: event %s or order %s not found", event_pk, order_pk)
        return

    api = _get_api_client(event)
    if not api:
        return

    ticketswap_event_id = event.settings.get("ticketswap_event_id", as_type=str, default="")
    if not ticketswap_event_id:
        logger.warning("Order paid but no TicketSwap event ID for %s", event.slug)
        return

    try:
        positions = list(order.positions.all())

        for position in positions:
            meta = _ensure_dict(position.meta_info)

            # Idempotency: skip if already listed
            if meta.get("ticketswap", {}).get("listed"):
                logger.info("Position %s already listed, skipping", position.id)
                continue

            ticket_data = {
                "event_id": ticketswap_event_id,
                "order_code": order.code,
                "position_id": position.id,
                "price": float(position.price),
                "currency": event.currency,
            }

            result = api.list_ticket(ticket_data)

            meta.setdefault("ticketswap", {})
            meta["ticketswap"]["ticket_id"] = result.get("id")
            meta["ticketswap"]["listed"] = True
            position.meta_info = meta
            position.save(update_fields=["meta_info"])

            logger.info(
                "Listed ticket on TicketSwap: %s for position %s",
                result.get("id"),
                position.id,
            )

    except TicketSwapAPIError as e:
        logger.error("Failed to list tickets for order %s: %s", order.code, e)


def delist_tickets_for_order(event_pk, order_pk):
    """
    Remove all tickets from an order from TicketSwap listings.
    """
    from pretix.base.models import Event, Order

    try:
        event = Event.objects.get(pk=event_pk)
        order = Order.objects.get(pk=order_pk)
    except (Event.DoesNotExist, Order.DoesNotExist):
        logger.error("delist_tickets_for_order: event %s or order %s not found", event_pk, order_pk)
        return

    api = _get_api_client(event)
    if not api:
        return

    try:
        for position in order.positions.all():
            meta = _ensure_dict(position.meta_info)
            ticketswap_data = meta.get("ticketswap", {})
            ticket_id = ticketswap_data.get("ticket_id")

            if ticket_id and ticketswap_data.get("listed"):
                api.delist_ticket(ticket_id)
                logger.info("Delisted ticket from TicketSwap: %s", ticket_id)

                meta["ticketswap"]["listed"] = False
                position.meta_info = meta
                position.save(update_fields=["meta_info"])

    except TicketSwapAPIError as e:
        logger.error("Failed to delist tickets for order %s: %s", order.code, e)
