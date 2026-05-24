"""
Spec-conformant payload serialization for SecureSwap responses.

Pretix and SecureSwap model events differently, so this module owns the
translation: stable opaque IDs (UUID5), date formatting, price unit
conventions (minor vs. major), and venue inference.
"""

import uuid
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

# Stable namespace so the same Pretix object always serializes to the same UUID
# across processes and restarts. Generated once, hard-coded.
_NAMESPACE = uuid.UUID("a7d3f5e1-2c4b-4f8a-9d6e-1b3c5a7e9f0d")


def stable_uuid(*parts: str) -> str:
    """UUID5 of the joined parts under our plugin namespace."""
    return str(uuid.uuid5(_NAMESPACE, "|".join(parts)))


def event_uuid(event) -> str:
    return stable_uuid("event", str(event.pk))


def item_uuid(item) -> str:
    return stable_uuid("item", str(item.pk))


def venue_uuid(event) -> str:
    # Pretix doesn't have a separate Venue model; venue is event-scoped.
    return stable_uuid("venue", str(event.pk))


def position_uuid(position) -> str:
    return stable_uuid("position", str(position.pk))


def _to_decimal(amount) -> Decimal:
    """Coerce ``amount`` to ``Decimal`` without inheriting float precision."""
    if isinstance(amount, Decimal):
        return amount
    if isinstance(amount, (int,)):
        return Decimal(amount)
    # Going via str avoids Decimal(0.99) producing 0.9899999999999...
    return Decimal(str(amount))


def _money_string(amount) -> str:
    """SecureSwap MoneyString: human-format `15.00`."""
    if amount is None:
        return "0.00"
    return f"{_to_decimal(amount):.2f}"


def _money_minor_units(amount) -> int:
    """SecureSwap GenericTicketType: integer cents/pennies."""
    if amount is None:
        return 0
    return int((_to_decimal(amount) * 100).quantize(Decimal("1")))


def _format_dt(dt) -> Optional[str]:
    """ISO 8601 with timezone, the format the spec requires."""
    if dt is None:
        return None
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)


def serialize_ticket_type(item, position=None) -> Dict[str, Any]:
    """Used by /validate and the embedded ``type`` field on tickets.

    MoneyString form (`"15.00"`), since this is what `Event` / `TicketType`
    schemas in the spec use.
    """
    price = position.price if position is not None else getattr(item, "default_price", 0)
    return {
        "id": item_uuid(item),
        "name": str(item.name) if item else "",
        "date_start": _format_dt(getattr(item.event, "date_from", None)) if item else None,
        "date_end": _format_dt(getattr(item.event, "date_to", None)) if item else None,
        "date_only": False,
        "price": _money_string(price),
        "service_fee": _money_string(0),  # Pretix has no separate service-fee field
        "currency": item.event.currency if item else "EUR",
    }


def serialize_validation_event(event) -> Dict[str, Any]:
    """Shape used inside /validate's ``event`` field (simpler than GenericEvent)."""
    sealed_at = event.settings.get(
        "ticketswap_sealed_available_at", as_type=str, default=""
    ) or None
    return {
        "id": event_uuid(event),
        "name": str(event.name),
        "date_start": _format_dt(event.date_from),
        "date_end": _format_dt(event.date_to),
        "date_only": False,
        "sealed_tickets_available_at": sealed_at,
    }


def _event_type(event) -> str:
    """Map Pretix to SecureSwap's event-type enum.

    Pretix has no built-in event type, so we honor a per-event override and
    default to OTHER. Valid values are enumerated in the spec; we coerce
    unknowns back to OTHER.
    """
    valid = {
        "FESTIVAL", "CONCERT", "CLUB", "THEATRE", "SPORT", "CONFERENCE",
        "EXHIBITION", "COMEDY", "WORKSHOP", "TALK", "SCREENING", "PARTY",
        "MUSEUM", "AMUSEMENT-PARK", "OTHER",
    }
    override = event.settings.get(
        "ticketswap_event_type", as_type=str, default="OTHER"
    ) or "OTHER"
    override = override.upper()
    return override if override in valid else "OTHER"


def _venue(event) -> Dict[str, Any]:
    """Inferred venue. Per-event settings override the heuristic.

    Pretix stores ``location`` as a free-text LazyI18nString; the best we
    can do without partner-supplied structure is a heuristic split on
    commas, plus per-event admin overrides for city / country.
    """
    name = event.settings.get(
        "ticketswap_venue_name", as_type=str, default=""
    ) or str(event.location or event.name)
    city = event.settings.get(
        "ticketswap_venue_city", as_type=str, default=""
    )
    country = event.settings.get(
        "ticketswap_venue_country", as_type=str, default=""
    )

    if (not city or not country) and event.location:
        # location is often "Venue Name, City, Country"
        parts = [p.strip() for p in str(event.location).split(",") if p.strip()]
        if len(parts) >= 3:
            city = city or parts[-2]
            country = country or parts[-1]
        elif len(parts) == 2:
            city = city or parts[-1]

    return {
        "id": venue_uuid(event),
        "name": name,
        "city": city or "Unknown",
        "country": (country or "NL")[:2].upper(),
    }


def serialize_generic_ticket_type(item) -> Dict[str, Any]:
    """For /events list: minor-unit pricing per the GenericTicketType schema."""
    return {
        "id": item_uuid(item),
        "name": str(item.name),
        "price": _money_minor_units(item.default_price),
        "service_fee": 0,
        "currency": item.event.currency,
        "date": {
            "start": _format_dt(item.event.date_from),
            "end": _format_dt(item.event.date_to),
        },
    }


def serialize_generic_event(event, items: Optional[Iterable] = None) -> Dict[str, Any]:
    """For /events list and /events/{id}.

    ``items`` defaults to all admission items of the event when not supplied;
    callers that already have the queryset can pass it in to avoid a second
    fetch.
    """
    if items is None:
        items = event.items.filter(active=True, admission=True)

    sealed_at = event.settings.get(
        "ticketswap_sealed_available_at", as_type=str, default=""
    ) or None
    swap_until = event.settings.get(
        "ticketswap_swap_available_until", as_type=str, default=""
    ) or None

    return {
        "id": event_uuid(event),
        "name": str(event.name),
        "type": _event_type(event),
        "sealed_tickets_available_at": sealed_at,
        "swap_available_until": swap_until,
        "date": {
            "start": _format_dt(event.date_from),
            "end": _format_dt(event.date_to),
        },
        "ticket_types": [serialize_generic_ticket_type(i) for i in items],
        "venue": _venue(event),
    }


def serialize_ticket_listing(position) -> Dict[str, Any]:
    """For /tickets/{uniqueIdentifier} list responses.

    Uses the same UUIDs as the other endpoints so a partner can correlate
    tickets across calls.
    """
    item = position.item
    barcode_type = position.event.settings.get(
        "ticketswap_barcode_type", as_type=str, default="QR-Code"
    ) or "QR-Code"

    return {
        "id": position_uuid(position),
        "swappable": True,
        "display_name": _display_name(position) or "Ticket",
        "barcode": position.secret,
        "barcode_type": barcode_type,
        "event": {
            "id": event_uuid(position.order.event),
            "name": str(position.order.event.name),
        },
        "ticket_type": {
            "id": item_uuid(item),
            "name": str(item.name) if item else "",
            "price": _money_minor_units(position.price),
            "service_fee": 0,
            "currency": position.order.event.currency,
        },
    }


def _display_name(position) -> str:
    name = (
        getattr(position, "attendee_name_cached", None)
        or getattr(position, "attendee_name", None)
        or ""
    )
    if not name:
        order = getattr(position, "order", None)
        ia = getattr(order, "invoice_address", None) if order else None
        if ia:
            name = getattr(ia, "name_cached", None) or ""
    return (name or "").split(" ")[0] if name else ""


def filter_admission_items(event) -> List:
    return list(event.items.filter(active=True, admission=True))
