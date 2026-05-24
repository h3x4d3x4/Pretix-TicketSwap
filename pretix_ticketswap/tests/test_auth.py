"""Bearer-token extraction + UNAUTHORIZED response shape."""

from unittest.mock import patch

from django.test import RequestFactory

from ..auth import _extract_bearer, _unauthorized, authenticate_partner


def _request_with_header(value=None):
    factory = RequestFactory()
    headers = {"HTTP_AUTHORIZATION": value} if value is not None else {}
    return factory.get("/", **headers)


def test_extract_bearer_token():
    req = _request_with_header("Bearer abc123")
    assert _extract_bearer(req) == "abc123"


def test_extract_bearer_case_insensitive_scheme():
    req = _request_with_header("bearer xyz")
    assert _extract_bearer(req) == "xyz"


def test_extract_bearer_rejects_other_schemes():
    req = _request_with_header("Basic abcdef")
    assert _extract_bearer(req) == ""


def test_extract_bearer_empty_when_missing():
    req = _request_with_header(None)
    assert _extract_bearer(req) == ""


def test_unauthorized_response_shape_matches_spec():
    """Spec ErrorResponse: barcode, valid, swappable, error."""
    response = _unauthorized("XYZ")
    assert response.status_code == 401
    import json
    body = json.loads(response.content.decode())
    assert body == {
        "barcode": "XYZ",
        "valid": False,
        "swappable": False,
        "error": "UNAUTHORIZED",
    }


class _FakeSettings:
    def __init__(self, token):
        self.token = token

    def get(self, key, as_type=str, default=""):
        return self.token if key == "ticketswap_partner_token" else default


class _FakeOrganizer:
    def __init__(self, slug, token):
        self.slug = slug
        self.settings = _FakeSettings(token)


@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_authenticate_partner_accepts_matching_token(mock_lookup):
    mock_lookup.return_value = _FakeOrganizer("org", token="secret-token")
    req = _request_with_header("Bearer secret-token")
    organizer, error = authenticate_partner(req, "org")
    assert organizer is not None
    assert error is None


@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_authenticate_partner_rejects_wrong_token(mock_lookup):
    mock_lookup.return_value = _FakeOrganizer("org", token="real-token")
    req = _request_with_header("Bearer wrong-token")
    organizer, error = authenticate_partner(req, "org")
    assert organizer is None
    assert error is not None
    assert error.status_code == 401


@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_authenticate_partner_rejects_missing_token(mock_lookup):
    mock_lookup.return_value = _FakeOrganizer("org", token="real-token")
    req = _request_with_header(None)
    organizer, error = authenticate_partner(req, "org")
    assert organizer is None
    assert error.status_code == 401


@patch("pretix_ticketswap.auth.organizer_with_secureswap_or_404")
def test_authenticate_partner_rejects_when_no_token_configured(mock_lookup):
    """A misconfigured organizer must not accept any inbound token."""
    mock_lookup.return_value = _FakeOrganizer("org", token="")
    req = _request_with_header("Bearer anything")
    organizer, error = authenticate_partner(req, "org")
    assert organizer is None
    assert error.status_code == 401
