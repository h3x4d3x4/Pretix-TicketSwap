"""
Unit tests for TicketSwap API client.
"""

import hashlib
import hmac
from unittest.mock import Mock, patch

import pytest
from django.test import TestCase

from ..ticketswap_api import TicketSwapAPI, TicketSwapAPIError, TicketSwapAuthError


class TicketSwapAPITestCase(TestCase):
    """Test cases for TicketSwap API client."""

    def setUp(self):
        """Set up test fixtures."""
        self.api_key = "test_api_key"
        self.api_secret = "test_api_secret"

    def test_sandbox_mode_initialization(self):
        """Test API client initializes in sandbox mode without credentials."""
        api = TicketSwapAPI()
        assert api.sandbox_mode is True
        assert api.api_key is None
        assert api.api_secret is None

    def test_live_mode_initialization(self):
        """Test API client initializes in live mode with credentials."""
        api = TicketSwapAPI(self.api_key, self.api_secret)
        assert api.sandbox_mode is False
        assert api.api_key == self.api_key
        assert api.api_secret == self.api_secret

    def test_mock_create_event(self):
        """Test creating an event in sandbox mode."""
        api = TicketSwapAPI()
        event_data = {
            "name": "Test Event",
            "date": "2026-06-01T20:00:00Z",
            "location": "Test Venue",
        }

        result = api.create_event(event_data)

        assert result["name"] == "Test Event"
        assert "id" in result
        assert result["status"] == "active"

    def test_mock_list_ticket(self):
        """Test listing a ticket in sandbox mode."""
        api = TicketSwapAPI()
        ticket_data = {
            "event_id": "mock_event_123",
            "price": 50.00,
            "currency": "EUR",
        }

        result = api.list_ticket(ticket_data)

        assert "id" in result
        assert result["event_id"] == "mock_event_123"
        assert result["status"] == "listed"

    def test_mock_delist_ticket(self):
        """Test delisting a ticket in sandbox mode."""
        api = TicketSwapAPI()
        result = api.delist_ticket("ticket_123")

        assert result["success"] is True
        assert result["status"] == "delisted"

    def test_mock_update_event(self):
        """Test updating an event in sandbox mode."""
        api = TicketSwapAPI()
        result = api.update_event("event_123", {"name": "Updated Event"})

        assert result["updated"] is True

    def test_mock_secureswap(self):
        """Test SecureSwap in sandbox mode."""
        api = TicketSwapAPI()
        buyer_data = {
            "name": "John Doe",
            "email": "john@example.com",
        }

        result = api.secureswap_ticket("old_ticket_123", buyer_data)

        assert result["success"] is True
        assert "new_ticket_id" in result
        assert "new_barcode" in result

    def test_connection_test_sandbox(self):
        """Test connection testing in sandbox mode."""
        api = TicketSwapAPI()
        assert api.test_connection() is True

    @patch("pretix_ticketswap.ticketswap_api._shared_session")
    def test_live_api_request(self, mock_session):
        """Test making a live API request."""
        api = TicketSwapAPI(self.api_key, self.api_secret)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "event_123", "name": "Test Event"}
        mock_session.request.return_value = mock_response

        result = api.create_event({"name": "Test Event"})

        assert result["id"] == "event_123"
        assert result["name"] == "Test Event"
        mock_session.request.assert_called_once()

    @patch("pretix_ticketswap.ticketswap_api._shared_session")
    def test_auth_error(self, mock_session):
        """Test handling of authentication errors."""
        api = TicketSwapAPI(self.api_key, self.api_secret)

        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = Exception("Unauthorized")
        mock_session.request.return_value = mock_response

        with pytest.raises(TicketSwapAuthError):
            api.create_event({"name": "Test Event"})

    def test_webhook_signature_verification(self):
        """Test webhook signature verification."""
        api = TicketSwapAPI()
        payload = b'{"event": "ticket.sold", "ticket_id": "123"}'
        secret = "webhook_secret"

        valid_signature = hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()

        assert api.verify_webhook_signature(payload, valid_signature, secret) is True
        assert api.verify_webhook_signature(payload, "invalid_sig", secret) is False

    def test_ssrf_guard(self):
        """Test that absolute URLs and protocol-relative paths are rejected."""
        api = TicketSwapAPI(self.api_key, self.api_secret)

        with pytest.raises(TicketSwapAPIError, match="Invalid endpoint"):
            api._make_request("GET", "//evil.com/path")

        with pytest.raises(TicketSwapAPIError, match="Invalid endpoint"):
            api._make_request("GET", "https://evil.com/events")

        with pytest.raises(TicketSwapAPIError, match="Invalid endpoint"):
            api._make_request("GET", "/absolute/path")

    def test_sandbox_mode_is_instance_attribute(self):
        """Test that sandbox_mode is per-instance, not shared via class variable."""
        sandbox_api = TicketSwapAPI()
        live_api = TicketSwapAPI("key", "secret")

        assert sandbox_api.sandbox_mode is True
        assert live_api.sandbox_mode is False
        # Changing one doesn't affect the other
        assert sandbox_api.sandbox_mode is True
