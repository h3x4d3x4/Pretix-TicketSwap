"""Signed-token round-trip + provider selection logic."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.signing import BadSignature, SignatureExpired

from ..pdf import (
    PDF_TOKEN_MAX_AGE,
    _resolve_position_from_token,
    _select_pdf_provider,
    _signer,
    signed_token_for_position,
)


def test_signed_token_roundtrip():
    position = SimpleNamespace(pk=42)
    token = signed_token_for_position(position)
    unsigned = _signer().unsign(token, max_age=PDF_TOKEN_MAX_AGE)
    assert unsigned == "42"


def test_signed_token_is_url_safe():
    position = SimpleNamespace(pk=42)
    token = signed_token_for_position(position)
    # Django's TimestampSigner uses URL-safe base64; should not need encoding.
    assert all(c.isalnum() or c in "-._:" for c in token)


def test_bad_signature_raises():
    with pytest.raises(BadSignature):
        _signer().unsign("totally:not:a:valid:token")


def test_resolve_position_404_on_bad_token():
    from django.http import Http404
    with pytest.raises(Http404):
        _resolve_position_from_token("not-a-token")


def test_resolve_position_404_on_expired_token():
    """An expired token returns Http404 via the SignatureExpired path."""
    from django.http import Http404
    with patch("pretix_ticketswap.pdf._signer") as mock_signer:
        mock_signer.return_value.unsign.side_effect = SignatureExpired("expired")
        with pytest.raises(Http404):
            _resolve_position_from_token("anything")


def test_select_pdf_provider_returns_pdf_provider():
    pdf_provider = SimpleNamespace(identifier="pdf")
    other_provider = SimpleNamespace(identifier="passbook")
    event = SimpleNamespace(slug="e")
    # register_ticket_outputs.send returns [(receiver, response_callable), ...]
    fake_responses = [
        (None, lambda _e: other_provider),
        (None, lambda _e: pdf_provider),
    ]
    with patch("pretix.base.signals.register_ticket_outputs.send",
               return_value=fake_responses):
        assert _select_pdf_provider(event) is pdf_provider


def test_select_pdf_provider_returns_none_when_no_providers():
    event = SimpleNamespace(slug="e")
    with patch("pretix.base.signals.register_ticket_outputs.send", return_value=[]):
        assert _select_pdf_provider(event) is None


def test_select_pdf_provider_handles_signal_exception():
    event = SimpleNamespace(slug="e")
    with patch("pretix.base.signals.register_ticket_outputs.send",
               side_effect=RuntimeError("no!")):
        assert _select_pdf_provider(event) is None


def test_select_pdf_provider_falls_back_to_first_non_pdf():
    """If no provider has identifier='pdf', we use whatever's available."""
    other_provider = SimpleNamespace(identifier="passbook")
    event = SimpleNamespace(slug="e")
    with patch("pretix.base.signals.register_ticket_outputs.send",
               return_value=[(None, lambda _e: other_provider)]):
        assert _select_pdf_provider(event) is other_provider


def _bad_provider_init(_e):
    raise RuntimeError("boom")


def test_select_pdf_provider_skips_provider_that_fails_to_instantiate():
    pdf_provider = SimpleNamespace(identifier="pdf")
    event = SimpleNamespace(slug="e")
    fake_responses = [
        (None, _bad_provider_init),
        (None, lambda _e: pdf_provider),
    ]
    with patch("pretix.base.signals.register_ticket_outputs.send",
               return_value=fake_responses):
        assert _select_pdf_provider(event) is pdf_provider
