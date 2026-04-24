"""Extra API-client tests covering idempotency, error mapping, and signature prefixes."""

import hashlib
import hmac
from unittest.mock import Mock, patch

import pytest

from ..ticketswap_api import (
    TicketSwapAPI,
    TicketSwapAuthError,
    TicketSwapNotFoundError,
    TicketSwapRateLimitError,
)


def _response(status_code, json_body=None, content=b""):
    r = Mock()
    r.status_code = status_code
    r.text = ""
    r.content = content or (b"{}" if json_body is not None else b"")
    r.json.return_value = json_body if json_body is not None else {}
    return r


@patch("pretix_ticketswap.ticketswap_api._shared_session")
def test_post_includes_idempotency_key(mock_session):
    api = TicketSwapAPI("key", "secret")
    mock_session.request.return_value = _response(200, {"id": "x"})
    api.create_event({"name": "E", "slug": "e"})
    call_kwargs = mock_session.request.call_args.kwargs
    headers = call_kwargs["headers"]
    assert "Idempotency-Key" in headers
    assert headers["Idempotency-Key"]


@patch("pretix_ticketswap.ticketswap_api._shared_session")
def test_idempotency_key_stable_for_create_event(mock_session):
    api = TicketSwapAPI("key", "secret")
    mock_session.request.return_value = _response(200, {"id": "x"})

    api.create_event({"name": "E", "slug": "e"})
    first = mock_session.request.call_args.kwargs["headers"]["Idempotency-Key"]
    api.create_event({"name": "E", "slug": "e"})
    second = mock_session.request.call_args.kwargs["headers"]["Idempotency-Key"]
    assert first == second  # same input → same key, server can dedupe


@patch("pretix_ticketswap.ticketswap_api._shared_session")
def test_get_does_not_include_idempotency_key(mock_session):
    api = TicketSwapAPI("key", "secret")
    mock_session.request.return_value = _response(200, {"id": "x"})
    api.get_event("x")
    headers = mock_session.request.call_args.kwargs["headers"]
    assert "Idempotency-Key" not in headers


@patch("pretix_ticketswap.ticketswap_api._shared_session")
def test_404_raises_specific_error(mock_session):
    api = TicketSwapAPI("key", "secret")
    mock_session.request.return_value = _response(404)
    with pytest.raises(TicketSwapNotFoundError):
        api.get_event("missing")


@patch("pretix_ticketswap.ticketswap_api._shared_session")
def test_429_raises_rate_limit(mock_session):
    api = TicketSwapAPI("key", "secret")
    mock_session.request.return_value = _response(429)
    with pytest.raises(TicketSwapRateLimitError):
        api.get_event("x")


@patch("pretix_ticketswap.ticketswap_api._shared_session")
def test_403_raises_auth_error(mock_session):
    api = TicketSwapAPI("key", "secret")
    mock_session.request.return_value = _response(403)
    with pytest.raises(TicketSwapAuthError):
        api.get_event("x")


def test_verify_signature_with_sha256_prefix():
    api = TicketSwapAPI()
    payload = b'{"event": "ticket.sold"}'
    secret = "s3cr3t"
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert api.verify_webhook_signature(payload, f"sha256={expected}", secret) is True


def test_verify_signature_rejects_empty_inputs():
    api = TicketSwapAPI()
    assert api.verify_webhook_signature(b"body", "", "secret") is False
    assert api.verify_webhook_signature(b"body", "abc", "") is False


def test_empty_credentials_fall_to_sandbox():
    """Blank strings must not be treated as valid credentials."""
    api = TicketSwapAPI("", "")
    assert api.sandbox_mode is True

    api = TicketSwapAPI("key", "")
    assert api.sandbox_mode is True  # one-sided config stays sandbox

    api = TicketSwapAPI("", "secret")
    assert api.sandbox_mode is True


def test_only_idempotent_methods_in_retry_whitelist():
    """POST/PUT/DELETE must NOT be retried automatically.

    We handle POST idempotency with the Idempotency-Key header; auto-retrying
    at the HTTP layer would bypass that semantic on unsupported servers.
    """
    from ..ticketswap_api import _create_shared_session
    s = _create_shared_session()
    adapter = s.get_adapter("https://api.ticketswap.com/")
    # Retry.allowed_methods is normalized to frozenset of uppercased strings
    allowed = adapter.max_retries.allowed_methods
    assert "POST" not in allowed
    assert "DELETE" not in allowed
    assert "PUT" not in allowed
    assert "GET" in allowed
