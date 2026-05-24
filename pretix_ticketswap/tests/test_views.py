"""
Smoke tests for the partner endpoints.

These cover the auth gating + spec-shaped response bodies via heavy
mocking of the DB layer. End-to-end happy-path coverage is intended
to live in the pretix-test environment, not here.
"""

import json
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory

from ..serializers import event_uuid, position_uuid
from ..views import (
    EventGetView,
    EventsListView,
    LockView,
    PersonalizationFieldsView,
    PersonalizeView,
    SwapView,
    TicketsListView,
    ValidateView,
)


def _factory():
    return RequestFactory()


class _FakeOrganizerSettings:
    def __init__(self, token):
        self._token = token

    def get(self, key, as_type=str, default=""):
        return self._token if key == "ticketswap_partner_token" else default


def _fake_organizer(token="t0k3n"):
    return SimpleNamespace(slug="org", settings=_FakeOrganizerSettings(token))


def _fake_event_settings(overrides=None):
    o = overrides or {}

    class S:
        def get(self, key, as_type=str, default=False):
            if key in o:
                return o[key]
            return default
    return S()


def _fake_event(pk=1, slug="e", currency="EUR", settings_overrides=None):
    return SimpleNamespace(
        pk=pk, slug=slug, currency=currency, name="Test Event",
        date_from=datetime(2026, 7, 12, 10, 0, tzinfo=timezone.utc),
        date_to=datetime(2026, 7, 13, 23, 0, tzinfo=timezone.utc),
        location="Venue, City, NL",
        settings=_fake_event_settings(settings_overrides),
        items=SimpleNamespace(filter=lambda **_: []),
        get_ticket_providers=lambda: [],
    )


def _fake_position(secret="BARCODE-1", event=None, canceled=False, price="20.00",
                   meta="", status="p"):
    """Default ``status="p"`` is Pretix's STATUS_PAID — required for resale."""
    e = event or _fake_event()
    item = SimpleNamespace(pk=10, name="GA", default_price=Decimal(price), event=e)
    return SimpleNamespace(
        pk=99, secret=secret, canceled=canceled, price=Decimal(price),
        meta_info=meta,
        item=item,
        attendee_name_cached="Alice Doe", attendee_name=None,
        attendee_email=None,
        order=SimpleNamespace(
            event=e, status=status, code="ORD1",
            invoice_address=None,
            datetime=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        event=e,
    )


# ---- Auth gating ----------------------------------------------------------


@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_validate_rejects_missing_token(mock_lookup):
    mock_lookup.return_value = _fake_organizer(token="real")
    req = _factory().get("/_secureswap/api/org/validate?barcode=X")
    response = ValidateView.as_view()(req, organizer="org")
    assert response.status_code == 401


@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_validate_rejects_wrong_token(mock_lookup):
    mock_lookup.return_value = _fake_organizer(token="real")
    req = _factory().get(
        "/_secureswap/api/org/validate?barcode=X",
        HTTP_AUTHORIZATION="Bearer wrong",
    )
    response = ValidateView.as_view()(req, organizer="org")
    assert response.status_code == 401
    body = json.loads(response.content.decode())
    assert body["error"] == "UNAUTHORIZED"


# ---- Validate -------------------------------------------------------------


@patch("pretix_ticketswap.views.find_position_by_revoked_barcode", return_value=None)
@patch("pretix_ticketswap.views.find_position_by_barcode")
@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_validate_unknown_barcode_returns_404(mock_lookup, mock_find, _mock_revoked):
    mock_lookup.return_value = _fake_organizer()
    mock_find.return_value = None
    req = _factory().get(
        "/_secureswap/api/org/validate?barcode=NOPE",
        HTTP_AUTHORIZATION="Bearer t0k3n",
    )
    response = ValidateView.as_view()(req, organizer="org")
    assert response.status_code == 404
    body = json.loads(response.content.decode())
    assert body["error"] == "TICKET_NOT_FOUND"


@patch("pretix_ticketswap.views.find_position_by_revoked_barcode")
@patch("pretix_ticketswap.views.find_position_by_barcode")
@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_validate_revoked_barcode_returns_already_swapped(
    mock_lookup, mock_find, mock_revoked,
):
    mock_lookup.return_value = _fake_organizer()
    mock_find.return_value = None
    mock_revoked.return_value = _fake_position()
    req = _factory().get(
        "/_secureswap/api/org/validate?barcode=OLD",
        HTTP_AUTHORIZATION="Bearer t0k3n",
    )
    response = ValidateView.as_view()(req, organizer="org")
    # Spec: 200 + ErrorResponse for business-rule rejects
    assert response.status_code == 200
    body = json.loads(response.content.decode())
    assert body["error"] == "TICKET_ALREADY_SWAPPED"


@patch("pretix_ticketswap.views.find_position_by_barcode")
@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_validate_happy_path_returns_validation_response(mock_lookup, mock_find):
    mock_lookup.return_value = _fake_organizer()
    pos = _fake_position()
    mock_find.return_value = pos
    req = _factory().get(
        "/_secureswap/api/org/validate?barcode=BARCODE-1",
        HTTP_AUTHORIZATION="Bearer t0k3n",
    )
    response = ValidateView.as_view()(req, organizer="org")
    assert response.status_code == 200
    body = json.loads(response.content.decode())
    assert body["valid"] is True
    assert body["swappable"] is True
    assert body["barcode"] == "BARCODE-1"
    assert body["id"] == position_uuid(pos)
    assert body["event"]["id"] == event_uuid(pos.order.event)


@patch("pretix_ticketswap.views.find_position_by_barcode")
@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_validate_free_ticket_returns_resell_not_allowed(mock_lookup, mock_find):
    mock_lookup.return_value = _fake_organizer()
    mock_find.return_value = _fake_position(price="0.00")
    req = _factory().get(
        "/_secureswap/api/org/validate?barcode=BARCODE-1",
        HTTP_AUTHORIZATION="Bearer t0k3n",
    )
    response = ValidateView.as_view()(req, organizer="org")
    # spec: 200 + ErrorResponse for business-rule rejects
    assert response.status_code == 200
    body = json.loads(response.content.decode())
    assert body["error"] == "RESELL_NOT_ALLOWED"
    assert body["valid"] is True   # ticket exists
    assert body["swappable"] is False


@patch("pretix_ticketswap.views.find_position_by_barcode")
@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_validate_unpaid_order_returns_resell_not_allowed(mock_lookup, mock_find):
    mock_lookup.return_value = _fake_organizer()
    mock_find.return_value = _fake_position(status="n")  # STATUS_PENDING
    req = _factory().get(
        "/_secureswap/api/org/validate?barcode=BARCODE-1",
        HTTP_AUTHORIZATION="Bearer t0k3n",
    )
    response = ValidateView.as_view()(req, organizer="org")
    body = json.loads(response.content.decode())
    assert body["error"] == "RESELL_NOT_ALLOWED"


@patch("pretix_ticketswap.views.find_position_by_barcode")
@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_validate_canceled_order_returns_order_cancelled(mock_lookup, mock_find):
    mock_lookup.return_value = _fake_organizer()
    mock_find.return_value = _fake_position(status="c")  # STATUS_CANCELED
    req = _factory().get(
        "/_secureswap/api/org/validate?barcode=BARCODE-1",
        HTTP_AUTHORIZATION="Bearer t0k3n",
    )
    response = ValidateView.as_view()(req, organizer="org")
    body = json.loads(response.content.decode())
    assert body["error"] == "ORDER_CANCELLED"


@patch("pretix_ticketswap.views.find_position_by_barcode")
@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_validate_response_carries_no_store_header(mock_lookup, mock_find):
    mock_lookup.return_value = _fake_organizer()
    mock_find.return_value = _fake_position()
    req = _factory().get(
        "/_secureswap/api/org/validate?barcode=BARCODE-1",
        HTTP_AUTHORIZATION="Bearer t0k3n",
    )
    response = ValidateView.as_view()(req, organizer="org")
    assert response["Cache-Control"] == "no-store"


# ---- Swap -----------------------------------------------------------------


@patch("pretix_ticketswap.views.swap_barcode", return_value="NEW-BARCODE")
@patch("pretix_ticketswap.views.find_position_by_barcode")
@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_swap_happy_path_returns_201_with_new_barcode(mock_lookup, mock_find, mock_swap):
    mock_lookup.return_value = _fake_organizer()
    pos = _fake_position()
    mock_find.return_value = pos
    req = _factory().post(
        "/_secureswap/api/org/swap",
        data=json.dumps({
            "ticket": {"barcode": "BARCODE-1"},
            "customer": {"firstName": "Bob", "lastName": "X",
                         "email": "b@x.com", "language": "en"},
        }),
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer t0k3n",
    )
    response = SwapView.as_view()(req, organizer="org")
    assert response.status_code == 201
    body = json.loads(response.content.decode())
    assert body["barcode"] == "NEW-BARCODE"
    assert body["id"] == position_uuid(pos)
    # No personalization required → pdf field present (None ok if no provider)
    assert "pdf" in body


@patch("pretix_ticketswap.views.find_position_by_barcode")
@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_swap_unknown_barcode_returns_404(mock_lookup, mock_find):
    mock_lookup.return_value = _fake_organizer()
    mock_find.return_value = None
    req = _factory().post(
        "/_secureswap/api/org/swap",
        data=json.dumps({"ticket": {"barcode": "NOPE"}, "customer": {}}),
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer t0k3n",
    )
    response = SwapView.as_view()(req, organizer="org")
    assert response.status_code == 404


@patch("pretix_ticketswap.views.find_position_by_barcode")
@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_swap_oversized_body_rejected(mock_lookup, mock_find):
    mock_lookup.return_value = _fake_organizer()
    huge_body = "x" * (70 * 1024)
    req = _factory().post(
        "/_secureswap/api/org/swap",
        data=huge_body,
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer t0k3n",
    )
    response = SwapView.as_view()(req, organizer="org")
    assert response.status_code in (400, 404)
    # find_position_by_barcode must not have been called — we bail before lookup.
    assert mock_find.call_count == 0


# ---- Personalize ----------------------------------------------------------


@patch("pretix_ticketswap.views.find_position_by_barcode")
@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_personalize_when_not_required_returns_200_with_pdf(mock_lookup, mock_find):
    mock_lookup.return_value = _fake_organizer()
    pos = _fake_position(event=_fake_event(
        settings_overrides={"ticketswap_personalization_required": False}
    ))
    mock_find.return_value = pos
    req = _factory().post(
        "/_secureswap/api/org/personalize",
        data=json.dumps({
            "ticket": {"barcode": pos.secret},
            "customer": {"firstName": "A", "lastName": "B",
                         "email": "a@b.com", "language": "en"},
        }),
        content_type="application/json",
        HTTP_AUTHORIZATION="Bearer t0k3n",
    )
    response = PersonalizeView.as_view()(req, organizer="org")
    assert response.status_code == 200
    body = json.loads(response.content.decode())
    assert body["barcode"] == pos.secret


# ---- Personalization fields ----------------------------------------------


@patch("pretix_ticketswap.views.find_position_by_barcode")
@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_personalization_fields_returns_defaults_when_unset(mock_lookup, mock_find):
    mock_lookup.return_value = _fake_organizer()
    mock_find.return_value = _fake_position()
    req = _factory().get(
        "/_secureswap/api/org/personalization-fields/BARCODE-1",
        HTTP_AUTHORIZATION="Bearer t0k3n",
    )
    response = PersonalizationFieldsView.as_view()(req, organizer="org", barcode="BARCODE-1")
    assert response.status_code == 200
    body = json.loads(response.content.decode())
    assert isinstance(body, list)
    assert any(f["name"] == "first_name" for f in body)


# ---- Events list ----------------------------------------------------------


@patch("pretix_ticketswap.views.page_events")
@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_events_list_pagination_shape(mock_lookup, mock_page):
    mock_lookup.return_value = _fake_organizer()
    e1 = _fake_event(pk=1, slug="e1")
    e2 = _fake_event(pk=2, slug="e2")
    mock_page.return_value = ([e1, e2], 47)
    req = _factory().get(
        "/_secureswap/api/org/events?page=1&page_size=20",
        HTTP_AUTHORIZATION="Bearer t0k3n",
    )
    response = EventsListView.as_view()(req, organizer="org")
    assert response.status_code == 200
    body = json.loads(response.content.decode())
    assert body["pagination"] == {
        "page": 1, "page_size": 20,
        "total_pages": 3, "total_results": 47,
    }
    assert len(body["events"]) == 2


# ---- Event get ------------------------------------------------------------


@patch("pretix_ticketswap.views.find_event_by_uuid")
@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_event_get_404_when_unknown(mock_lookup, mock_find):
    mock_lookup.return_value = _fake_organizer()
    mock_find.return_value = None
    req = _factory().get(
        "/_secureswap/api/org/events/some-uuid",
        HTTP_AUTHORIZATION="Bearer t0k3n",
    )
    response = EventGetView.as_view()(req, organizer="org", id="some-uuid")
    assert response.status_code == 404


# ---- Tickets list ---------------------------------------------------------


@patch("pretix_ticketswap.views.find_positions_for_unique_identifier")
@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_tickets_list_404_when_no_positions(mock_lookup, mock_find):
    mock_lookup.return_value = _fake_organizer()
    mock_find.return_value = []
    req = _factory().get(
        "/_secureswap/api/org/tickets/ORD1",
        HTTP_AUTHORIZATION="Bearer t0k3n",
    )
    response = TicketsListView.as_view()(req, organizer="org", uniqueIdentifier="ORD1")
    assert response.status_code == 404


@patch("pretix_ticketswap.views.find_positions_for_unique_identifier")
@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_tickets_list_returns_tickets_array(mock_lookup, mock_find):
    mock_lookup.return_value = _fake_organizer()
    mock_find.return_value = [_fake_position()]
    req = _factory().get(
        "/_secureswap/api/org/tickets/ORD1",
        HTTP_AUTHORIZATION="Bearer t0k3n",
    )
    response = TicketsListView.as_view()(req, organizer="org", uniqueIdentifier="ORD1")
    assert response.status_code == 200
    body = json.loads(response.content.decode())
    assert len(body["tickets"]) == 1


# ---- Lock -----------------------------------------------------------------


@patch("pretix_ticketswap.views.lock_position")
@patch("pretix_ticketswap.views.find_position_by_ticket_uuid")
@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_lock_returns_201_on_success(mock_lookup, mock_find, mock_lock):
    mock_lookup.return_value = _fake_organizer()
    mock_find.return_value = _fake_position()
    req = _factory().post(
        "/_secureswap/api/org/lock/some-uuid",
        HTTP_AUTHORIZATION="Bearer t0k3n",
    )
    response = LockView.as_view()(req, organizer="org", ticketId="some-uuid")
    assert response.status_code == 201
    assert mock_lock.called


@patch("pretix_ticketswap.views.unlock_position")
@patch("pretix_ticketswap.views.find_position_by_ticket_uuid")
@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_unlock_returns_204(mock_lookup, mock_find, mock_unlock):
    mock_lookup.return_value = _fake_organizer()
    mock_find.return_value = _fake_position()
    req = _factory().delete(
        "/_secureswap/api/org/lock/some-uuid",
        HTTP_AUTHORIZATION="Bearer t0k3n",
    )
    response = LockView.as_view()(req, organizer="org", ticketId="some-uuid")
    assert response.status_code == 204
    assert mock_unlock.called


@patch("pretix_ticketswap.views.find_position_by_ticket_uuid")
@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_lock_404_when_ticket_unknown(mock_lookup, mock_find):
    mock_lookup.return_value = _fake_organizer()
    mock_find.return_value = None
    req = _factory().post(
        "/_secureswap/api/org/lock/some-uuid",
        HTTP_AUTHORIZATION="Bearer t0k3n",
    )
    response = LockView.as_view()(req, organizer="org", ticketId="some-uuid")
    assert response.status_code == 404
