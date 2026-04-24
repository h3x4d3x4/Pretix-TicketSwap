"""
TicketSwap API Client.

Handles authentication, event sync, ticket listing, SecureSwap, and
webhook signature verification. Supports a credential-less sandbox
mode for development and tests.
"""

import hashlib
import hmac
import logging
import uuid
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Default per-request timeout: (connect, read)
DEFAULT_TIMEOUT = (5, 15)


def _create_shared_session():
    """Session with connection pooling + retry on transient errors only.

    We deliberately restrict retries to idempotent methods. A transient
    5xx on a POST would otherwise cause duplicate event creation or
    duplicate listings; we guard against that with an ``Idempotency-Key``
    header instead (see ``_make_request``).
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD", "OPTIONS"],
        respect_retry_after_header=True,
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
    """Base exception for TicketSwap API errors."""

    def __init__(self, message, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class TicketSwapAuthError(TicketSwapAPIError):
    """Authentication-related errors (401/403)."""


class TicketSwapNotFoundError(TicketSwapAPIError):
    """Resource not found (404)."""


class TicketSwapRateLimitError(TicketSwapAPIError):
    """Rate limit hit (429) after retries exhausted."""


class TicketSwapAPI:
    """Client for the TicketSwap REST API.

    Falls back to sandbox (mock) responses when constructed without
    credentials, so UI and signal paths are exercisable without a real
    partnership integration.
    """

    BASE_URL = "https://api.ticketswap.com/v1/"

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.api_key = api_key or None
        self.api_secret = api_secret or None
        self.sandbox_mode = not (self.api_key and self.api_secret)
        self.session = _shared_session

        if not self.sandbox_mode:
            self._headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "pretix-ticketswap-plugin",
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
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        if self.sandbox_mode:
            return self._mock_response(method, endpoint, data)

        # Guard against SSRF: reject absolute/protocol-relative/leading-slash endpoints
        if endpoint.startswith(("/", "http://", "https://", "//")):
            raise TicketSwapAPIError(f"Invalid endpoint: {endpoint}")

        url = urljoin(self.BASE_URL, endpoint)

        headers = dict(self._headers)
        if method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
            # Safe to retry on the server side because the key is stable per-call.
            headers["Idempotency-Key"] = idempotency_key or uuid.uuid4().hex

        try:
            response = self.session.request(
                method=method,
                url=url,
                json=data,
                params=params,
                timeout=DEFAULT_TIMEOUT,
                headers=headers,
            )
        except requests.exceptions.RequestException as e:
            logger.error("TicketSwap network error: %s", e)
            raise TicketSwapAPIError(f"Network error: {e}")

        status = response.status_code

        def _body():
            try:
                return (response.text or "")[:500]
            except Exception:
                return ""

        if status in (401, 403):
            raise TicketSwapAuthError(
                "Invalid API credentials" if status == 401 else "Forbidden",
                status_code=status,
                response_body=_body(),
            )
        if status == 404:
            raise TicketSwapNotFoundError(
                "Resource not found",
                status_code=status,
                response_body=_body(),
            )
        if status == 429:
            raise TicketSwapRateLimitError(
                "Rate limit exceeded",
                status_code=status,
                response_body=_body(),
            )
        if status >= 400:
            body = _body()
            logger.error("TicketSwap API error %s: %s", status, body)
            raise TicketSwapAPIError(
                f"API error {status}",
                status_code=status,
                response_body=body,
            )

        try:
            return response.json()
        except ValueError:
            raise TicketSwapAPIError("Invalid JSON in response", status_code=status)

    def _mock_response(
        self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
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
        if resource == "events" and method == "GET":
            if len(parts) > 1:
                return {"id": parts[1], "name": "Mock Event", "status": "active"}
            return {"items": [], "total": 0}
        if resource == "events" and method == "PUT":
            return {
                "id": parts[1] if len(parts) > 1 else "mock_event_123",
                "name": data.get("name", "Mock Event") if data else "Mock Event",
                "status": "active",
                "updated": True,
            }
        if resource == "tickets" and method == "POST":
            return {
                "id": "mock_ticket_456",
                "event_id": (data.get("event_id", "mock_event_123") if data else "mock_event_123"),
                "status": "listed",
                "created_at": "2026-01-18T03:00:00Z",
            }
        if resource == "tickets" and method == "DELETE":
            return {
                "success": True,
                "ticket_id": parts[1] if len(parts) > 1 else "unknown",
                "status": "delisted",
            }
        if resource == "secureswap":
            return {
                "success": True,
                "old_ticket_id": data.get("old_ticket_id") if data else None,
                "new_ticket_id": "mock_new_ticket_789",
                "new_barcode": "MOCK_BARCODE_XYZ",
            }

        return {"success": True, "message": "Mock response"}

    # ---- High-level operations -------------------------------------------

    def create_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Creating event on TicketSwap: %s", event_data.get("name"))
        # Stable key per (slug+name) so a retried identical call is deduped server-side.
        idem = hashlib.sha256(
            f"event:{event_data.get('slug')}:{event_data.get('name')}".encode()
        ).hexdigest()
        return self._make_request("POST", "events", data=event_data, idempotency_key=idem)

    def update_event(self, event_id: str, event_data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Updating TicketSwap event: %s", event_id)
        return self._make_request("PUT", f"events/{event_id}", data=event_data)

    def get_event(self, event_id: str) -> Dict[str, Any]:
        return self._make_request("GET", f"events/{event_id}")

    def list_ticket(self, ticket_data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(
            "Listing ticket on TicketSwap for event: %s", ticket_data.get("event_id")
        )
        idem = hashlib.sha256(
            f"ticket:{ticket_data.get('event_id')}:{ticket_data.get('position_id')}"
            f":{ticket_data.get('barcode')}".encode()
        ).hexdigest()
        return self._make_request(
            "POST", "tickets", data=ticket_data, idempotency_key=idem
        )

    def delist_ticket(self, ticket_id: str) -> Dict[str, Any]:
        logger.info("Delisting ticket from TicketSwap: %s", ticket_id)
        return self._make_request("DELETE", f"tickets/{ticket_id}")

    def secureswap_ticket(
        self, old_ticket_id: str, new_buyer_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        logger.info("Executing SecureSwap for ticket: %s", old_ticket_id)
        return self._make_request(
            "POST",
            "secureswap",
            data={"old_ticket_id": old_ticket_id, "buyer": new_buyer_data},
            idempotency_key=hashlib.sha256(
                f"secureswap:{old_ticket_id}".encode()
            ).hexdigest(),
        )

    # ---- Webhook helpers --------------------------------------------------

    @staticmethod
    def _strip_signature_prefix(signature: str) -> str:
        """Accept ``sha256=<hex>`` or bare hex signatures."""
        if not signature:
            return ""
        sig = signature.strip()
        if "=" in sig:
            _, _, rest = sig.partition("=")
            return rest.strip()
        return sig

    def verify_webhook_signature(
        self, payload: bytes, signature: str, secret: str
    ) -> bool:
        """Constant-time HMAC-SHA256 verification.

        Accepts either ``sha256=<hex>`` or a raw hex digest as ``signature``
        to stay compatible with whatever prefix convention TicketSwap uses.
        """
        if not signature or not secret:
            return False
        sig = self._strip_signature_prefix(signature)
        expected = hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        try:
            return hmac.compare_digest(sig, expected)
        except Exception:
            return False

    def test_connection(self) -> bool:
        """Verify credentials work by hitting a light endpoint."""
        try:
            if self.sandbox_mode:
                logger.info("Connection test: SANDBOX mode active")
                return True
            self._make_request("GET", "events", params={"limit": 1})
            logger.info("TicketSwap API connection successful")
            return True
        except TicketSwapAuthError:
            logger.warning("TicketSwap API connection: auth failed")
            return False
        except TicketSwapAPIError as e:
            logger.error("TicketSwap API connection failed: %s", e)
            return False
