"""
Form validation tests for the new partner-token + per-event settings.
"""

import json
from types import SimpleNamespace

from ..forms import TicketSwapEventForm, TicketSwapOrganizerForm


def _fake_event():
    class S:
        def __init__(self):
            self._d = {}

        def get(self, key, as_type=str, default=""):
            v = self._d.get(key, default)
            if as_type is bool:
                if isinstance(v, bool):
                    return v
                return str(v).lower() in ("true", "1", "yes", "on")
            return v

        def set(self, key, value):
            self._d[key] = value

    return SimpleNamespace(slug="e", settings=S())


def _fake_organizer():
    class S:
        def __init__(self):
            self._d = {}

        def get(self, key, as_type=str, default=""):
            return self._d.get(key, default)

        def set(self, key, value):
            self._d[key] = value

    return SimpleNamespace(slug="org", settings=S())


# ---- Organizer form ------------------------------------------------------


def test_organizer_form_rotate_token_generates_value():
    organizer = _fake_organizer()
    form = TicketSwapOrganizerForm(
        data={"ticketswap_partner_token": "", "rotate_token": "on"},
        organizer=organizer,
    )
    assert form.is_valid(), form.errors
    form.save_to_organizer(organizer)
    saved = organizer.settings.get("ticketswap_partner_token", default="")
    assert saved
    assert len(saved) > 20


def test_organizer_form_stores_explicit_token():
    organizer = _fake_organizer()
    form = TicketSwapOrganizerForm(
        data={"ticketswap_partner_token": "my-secret-token-123"},
        organizer=organizer,
    )
    assert form.is_valid(), form.errors
    form.save_to_organizer(organizer)
    assert organizer.settings.get("ticketswap_partner_token") == "my-secret-token-123"


def test_organizer_form_blank_leaves_existing_value():
    organizer = _fake_organizer()
    organizer.settings.set("ticketswap_partner_token", "existing-token")
    form = TicketSwapOrganizerForm(data={}, organizer=organizer)
    assert form.is_valid(), form.errors
    form.save_to_organizer(organizer)
    assert organizer.settings.get("ticketswap_partner_token") == "existing-token"


# ---- Event form ----------------------------------------------------------


def test_event_form_accepts_minimal_enable():
    event = _fake_event()
    form = TicketSwapEventForm(
        data={
            "ticketswap_enabled": "on",
            "ticketswap_event_type": "OTHER",
            "ticketswap_barcode_type": "QR-Code",
        },
        event=event,
    )
    assert form.is_valid(), form.errors
    form.save_to_event(event)
    assert event.settings.get("ticketswap_enabled", as_type=bool) is True


def test_event_form_rejects_invalid_country_code():
    event = _fake_event()
    form = TicketSwapEventForm(
        data={
            "ticketswap_enabled": "on",
            "ticketswap_event_type": "OTHER",
            "ticketswap_barcode_type": "QR-Code",
            "ticketswap_venue_country": "NLD",  # three letters → wrong
        },
        event=event,
    )
    assert not form.is_valid()
    assert "ticketswap_venue_country" in form.errors


def test_event_form_rejects_malformed_personalization_json():
    event = _fake_event()
    form = TicketSwapEventForm(
        data={
            "ticketswap_enabled": "on",
            "ticketswap_event_type": "OTHER",
            "ticketswap_barcode_type": "QR-Code",
            "ticketswap_personalization_fields": "{not json",
        },
        event=event,
    )
    assert not form.is_valid()
    assert "ticketswap_personalization_fields" in form.errors


def test_event_form_rejects_personalization_fields_with_unknown_type():
    event = _fake_event()
    cfg = [{"name": "x", "label": "X", "type": "BOGUS",
            "is_required": True, "sort_order": 0}]
    form = TicketSwapEventForm(
        data={
            "ticketswap_enabled": "on",
            "ticketswap_event_type": "OTHER",
            "ticketswap_barcode_type": "QR-Code",
            "ticketswap_personalization_fields": json.dumps(cfg),
        },
        event=event,
    )
    assert not form.is_valid()


def test_event_form_accepts_valid_personalization_fields():
    event = _fake_event()
    cfg = [
        {"name": "first_name", "label": "First", "type": "text",
         "is_required": True, "sort_order": 0},
    ]
    form = TicketSwapEventForm(
        data={
            "ticketswap_enabled": "on",
            "ticketswap_event_type": "OTHER",
            "ticketswap_barcode_type": "QR-Code",
            "ticketswap_personalization_fields": json.dumps(cfg),
        },
        event=event,
    )
    assert form.is_valid(), form.errors


def test_event_form_upcases_country():
    event = _fake_event()
    form = TicketSwapEventForm(
        data={
            "ticketswap_enabled": "on",
            "ticketswap_event_type": "OTHER",
            "ticketswap_barcode_type": "QR-Code",
            "ticketswap_venue_country": "nl",
        },
        event=event,
    )
    assert form.is_valid(), form.errors
    assert form.cleaned_data["ticketswap_venue_country"] == "NL"
