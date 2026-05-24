"""
Pure-unit tests for the spec serializers.

These don't touch the DB — they verify shape, types, and conventions
(MoneyString vs minor-unit integers, UUID stability, ISO 8601 dt).
"""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from ..serializers import (
    _money_minor_units,
    _money_string,
    event_uuid,
    item_uuid,
    position_uuid,
    serialize_generic_event,
    serialize_generic_ticket_type,
    serialize_ticket_listing,
    serialize_ticket_type,
    serialize_validation_event,
    stable_uuid,
    venue_uuid,
)


def _fake_event(pk=1, slug="lowlands", currency="EUR", date_from=None, date_to=None,
                location="Ziggo Dome, Amsterdam, NL", settings=None):
    if date_from is None:
        date_from = datetime(2026, 7, 12, 10, 0, tzinfo=timezone.utc)
    if date_to is None:
        date_to = datetime(2026, 7, 13, 23, 0, tzinfo=timezone.utc)

    s = settings or {}

    class FakeSettings:
        def get(self, key, as_type=str, default=""):
            return s.get(key, default)

    items_qs = SimpleNamespace(filter=lambda **_: [])
    return SimpleNamespace(
        pk=pk, slug=slug, currency=currency, name="Lowlands",
        date_from=date_from, date_to=date_to, location=location,
        settings=FakeSettings(),
        items=items_qs,
    )


def _fake_item(pk=10, name="Sunday", price="18.00", event=None):
    return SimpleNamespace(
        pk=pk, name=name, default_price=Decimal(price),
        event=event or _fake_event(),
        active=True, admission=True,
    )


def test_money_string_two_decimals():
    assert _money_string(Decimal("15")) == "15.00"
    assert _money_string(Decimal("15.5")) == "15.50"
    assert _money_string(None) == "0.00"


def test_money_minor_units_cents():
    assert _money_minor_units(Decimal("15.00")) == 1500
    assert _money_minor_units(Decimal("0.99")) == 99
    assert _money_minor_units(None) == 0


def test_stable_uuid_is_deterministic_and_distinct():
    a = stable_uuid("event", "1")
    b = stable_uuid("event", "1")
    c = stable_uuid("event", "2")
    assert a == b
    assert a != c


def test_event_uuid_is_stable_for_same_pk():
    e1 = _fake_event(pk=42)
    e2 = _fake_event(pk=42, slug="anything-else")
    assert event_uuid(e1) == event_uuid(e2)


def test_item_uuid_independent_of_event_uuid():
    assert item_uuid(_fake_item(pk=10)) != event_uuid(_fake_event(pk=10))


def test_position_uuid_distinct_from_item():
    pos = SimpleNamespace(pk=99)
    assert position_uuid(pos) != item_uuid(_fake_item(pk=99))


def test_venue_uuid_distinct_from_event_uuid():
    e = _fake_event(pk=5)
    assert venue_uuid(e) != event_uuid(e)


def test_serialize_validation_event_required_fields():
    e = _fake_event()
    out = serialize_validation_event(e)
    assert set(out) >= {"id", "name", "date_start", "date_end", "date_only"}
    assert out["date_only"] is False
    # ISO 8601 with timezone
    assert "T" in out["date_start"] and ("+" in out["date_start"] or "Z" in out["date_start"])


def test_serialize_ticket_type_uses_money_string():
    e = _fake_event()
    item = _fake_item(price="25.50", event=e)
    item.event = e
    pos = SimpleNamespace(price=Decimal("25.50"))
    out = serialize_ticket_type(item, pos)
    assert out["price"] == "25.50"
    assert out["service_fee"] == "0.00"
    assert out["currency"] == "EUR"


def test_serialize_generic_ticket_type_uses_minor_units():
    e = _fake_event()
    item = _fake_item(price="25.50", event=e)
    out = serialize_generic_ticket_type(item)
    assert out["price"] == 2550
    assert out["service_fee"] == 0
    assert out["currency"] == "EUR"
    assert set(out["date"]) == {"start", "end"}


def test_serialize_generic_event_includes_venue_and_type():
    e = _fake_event(location="Ziggo Dome, Amsterdam, NL")
    out = serialize_generic_event(e, items=[])
    assert out["type"] == "OTHER"
    assert out["venue"]["city"] == "Amsterdam"
    assert out["venue"]["country"] == "NL"
    assert out["ticket_types"] == []


def test_generic_event_honors_override_for_event_type():
    e = _fake_event(settings={"ticketswap_event_type": "FESTIVAL"})
    assert serialize_generic_event(e, items=[])["type"] == "FESTIVAL"


def test_generic_event_coerces_invalid_type_to_other():
    e = _fake_event(settings={"ticketswap_event_type": "NOPE"})
    assert serialize_generic_event(e, items=[])["type"] == "OTHER"


def test_ticket_listing_uses_position_secret_as_barcode():
    e = _fake_event()
    item = _fake_item(event=e)
    pos = SimpleNamespace(
        pk=1, secret="ABC123", price=Decimal("12.00"), item=item,
        attendee_name_cached="Alice Doe", attendee_name=None,
        order=SimpleNamespace(event=e, invoice_address=None),
        event=e,
    )
    out = serialize_ticket_listing(pos)
    assert out["barcode"] == "ABC123"
    assert out["display_name"] == "Alice"
    assert out["ticket_type"]["price"] == 1200
    assert out["barcode_type"] == "QR-Code"


def test_ticket_listing_honors_event_barcode_override():
    e = _fake_event(settings={"ticketswap_barcode_type": "CODE-128"})
    item = _fake_item(event=e)
    pos = SimpleNamespace(
        pk=2, secret="X", price=Decimal("1.00"), item=item,
        attendee_name_cached="", attendee_name="",
        order=SimpleNamespace(event=e, invoice_address=None),
        event=e,
    )
    assert serialize_ticket_listing(pos)["barcode_type"] == "CODE-128"
