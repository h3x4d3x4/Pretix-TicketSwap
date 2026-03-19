"""
TicketSwap API Client

Handles all communication with the TicketSwap API including:
- Authentication
- Event synchronization
- Ticket listing management
- SecureSwap integration
- Webhook verification
"""

import hashlib
import hmac
import logging
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


def _create_shared_session():
    """Create a shared session with connection pooling and retry logic."""
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST", "PUT", "DELETE"],
    )
    adapter = HTTPAdapter(
        max_retries=retry_strategy,
        pool_connections=10,
        pool_maxsize=10,
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


_shared_session = _create_shared_session()


class TicketSwapAPIError(Exception):
    """Base exception for TicketSwap API errors"""

    pass


class TicketSwapAuthError(TicketSwapAPIError):
    """Authentication-related errors"""

    pass


class TicketSwapAPI:
    """
    Client for interacting with the TicketSwap API.

    Supports both live API mode (with credentials) and mock/sandbox mode
    for development and testing.
    """

    BASE_URL = "https://api.ticketswap.com/v1/"

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        """
        Initialize the TicketSwap API client.

        Args:
            api_key: TicketSwap API key (optional for sandbox mode)
            api_secret: TicketSwap API secret (optional for sandbox mode)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.sandbox_mode = not (api_key and api_secret)
        self.session = _shared_session

        if not self.sandbox_mode:
            self._headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        else:
            self._headers = {}
            logger.info("TicketSwap API client initialized in SANDBOX mode")

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Make an HTTP request to the TicketSwap API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path
            data: Request body data
            params: URL query parameters

        Returns:
            Response data as dictionary

        Raises:
            TicketSwapAPIError: On API errors
            TicketSwapAuthError: On authentication errors
        """
        if self.sandbox_mode:
            return self._mock_response(method, endpoint, data)

        # Guard against SSRF via urljoin quirk
        if endpoint.startswith(("/", "http://", "https://", "//")):
            raise TicketSwapAPIError(f"Invalid endpoint: {endpoint}")

        url = urljoin(self.BASE_URL, endpoint)

        try:
            response = self.session.request(
                method=method,
                url=url,
                json=data,
                params=params,
                timeout=(5, 10),
                headers=self._headers,
            )

            if response.status_code == 401:
                raise TicketSwapAuthError("Invalid API credentials")

            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            logger.error("TicketSwap API HTTP error: %s", e)
            raise TicketSwapAPIError(f"API request failed: {e}")
        except requests.exceptions.RequestException as e:
            logger.error("TicketSwap API request error: %s", e)
            raise TicketSwapAPIError(f"Network error: {e}")

    def _mock_response(
        self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate mock responses for sandbox mode.

        Args:
            method: HTTP method
            endpoint: API endpoint
            data: Request data

        Returns:
            Mock response data
        """
        logger.info("[SANDBOX] %s %s", method, endpoint)
        logger.debug("[SANDBOX] Request data: %s", data)

        parts = endpoint.strip("/").split("/")
        resource = parts[0] if parts else ""

        if resource == "events" and method == "POST":
            return {
                "id": "mock_event_123",
                "name": data.get("name", "Mock Event") if data else "Mock Event",
                "status": "active",
                "created_at": "2026-01-18T03:00:00Z",
            }
        elif resource == "events" and method == "GET":
            return {
                "id": "mock_event_123",
                "name": "Mock Event",
                "status": "active",
            }
        elif resource == "events" and method == "PUT":
            return {
                "id": parts[1] if len(parts) > 1 else "mock_event_123",
                "name": data.get("name", "Mock Event") if data else "Mock Event",
                "status": "active",
                "updated": True,
            }
        elif resource == "tickets" and method == "POST":
            return {
                "id": "mock_ticket_456",
                "event_id": data.get("event_id", "mock_event_123") if data else "mock_event_123",
                "status": "listed",
                "created_at": "2026-01-18T03:00:00Z",
            }
        elif resource == "tickets" and method == "DELETE":
            return {
                "success": True,
                "ticket_id": parts[1] if len(parts) > 1 else "unknown",
                "status": "delisted",
            }
        elif resource == "secureswap":
            return {
                "success": True,
                "old_ticket_id": data.get("old_ticket_id") if data else None,
                "new_ticket_id": "mock_new_ticket_789",
                "new_barcode": "MOCK_BARCODE_XYZ",
            }

        return {"success": True, "message": "Mock response"}

    def create_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create an event on TicketSwap.

        Args:
            event_data: Event information (name, date, location, etc.)

        Returns:
            Created event data with TicketSwap event ID
        """
        logger.info("Creating event on TicketSwap: %s", event_data.get("name"))
        return self._make_request("POST", "events", data=event_data)

    def update_event(self, event_id: str, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing event on TicketSwap.

        Args:
            event_id: TicketSwap event ID
            event_data: Updated event information

        Returns:
            Updated event data
        """
        logger.info("Updating TicketSwap event: %s", event_id)
        return self._make_request("PUT", f"events/{event_id}", data=event_data)

    def get_event(self, event_id: str) -> Dict[str, Any]:
        """
        Retrieve event details from TicketSwap.

        Args:
            event_id: TicketSwap event ID

        Returns:
            Event data
        """
        return self._make_request("GET", f"events/{event_id}")

    def list_ticket(self, ticket_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        List a ticket for resale on TicketSwap.

        Args:
            ticket_data: Ticket information (event_id, price, barcode, etc.)

        Returns:
            Listed ticket data
        """
        logger.info("Listing ticket on TicketSwap for event: %s", ticket_data.get("event_id"))
        return self._make_request("POST", "tickets", data=ticket_data)

    def delist_ticket(self, ticket_id: str) -> Dict[str, Any]:
        """
        Remove a ticket from TicketSwap listings.

        Args:
            ticket_id: TicketSwap ticket ID

        Returns:
            Deletion confirmation
        """
        logger.info("Delisting ticket from TicketSwap: %s", ticket_id)
        return self._make_request("DELETE", f"tickets/{ticket_id}")

    def secureswap_ticket(
        self, old_ticket_id: str, new_buyer_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute SecureSwap: invalidate old ticket and generate new one.

        Args:
            old_ticket_id: Original ticket ID to invalidate
            new_buyer_data: New buyer information

        Returns:
            New ticket data with updated barcode
        """
        logger.info("Executing SecureSwap for ticket: %s", old_ticket_id)
        return self._make_request(
            "POST",
            "secureswap",
            data={"old_ticket_id": old_ticket_id, "buyer": new_buyer_data},
        )

    def verify_webhook_signature(
        self, payload: bytes, signature: str, secret: str
    ) -> bool:
        """
        Verify webhook signature from TicketSwap.

        Args:
            payload: Raw webhook payload
            signature: Signature from webhook headers
            secret: Webhook secret

        Returns:
            True if signature is valid
        """
        expected_signature = hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected_signature)

    def test_connection(self) -> bool:
        """
        Test API connection and credentials.

        Returns:
            True if connection is successful
        """
        try:
            if self.sandbox_mode:
                logger.info("Connection test: SANDBOX mode active")
                return True

            self._make_request("GET", "events", params={"limit": 1})
            logger.info("TicketSwap API connection successful")
            return True
        except Exception as e:
            logger.error("TicketSwap API connection failed: %s", e)
            return False
