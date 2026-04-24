# pretix-ticketswap

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Pretix 2024.7.0+](https://img.shields.io/badge/pretix-2024.7.0+-green.svg)](https://pretix.eu/)

A Pretix plugin that integrates with [TicketSwap](https://www.ticketswap.com/)'s secondary ticket marketplace, enabling secure ticket resale through SecureSwap technology.

## What it does

When installed on a Pretix event, the plugin automatically:

- **Syncs events** to TicketSwap when orders are placed
- **Lists tickets** for resale when orders are paid
- **Delists tickets** when orders are cancelled
- **Handles SecureSwap** — when a ticket is resold, the old barcode is invalidated and a new one is generated in Pretix so the buyer can enter the venue

Incoming TicketSwap webhooks are verified via HMAC-SHA256 and routed to the correct Pretix event. Replays are short-circuited with a cache-backed seen-set.

## Architecture

```
Signal handlers (signals.py)          Webhook endpoint (views.py)
        │                                      │
        ▼                                      ▼
  tasks.py                            Event lookup + signature verify
  (API logic, Celery-ready)                    │
        │                                      ▼
        ▼                              _handle_ticket_sold
  TicketSwapAPI client                 _handle_ticket_transferred  ← SecureSwap
  (ticketswap_api.py)                  _handle_ticket_cancelled
        │
        ▼
  TicketSwap REST API
  (shared session, connection pooling, retry)
```

**Key design decisions:**
- Signal handlers dispatch via `transaction.on_commit` so TicketSwap API work never blocks or rolls back a Pretix order — even a full API outage leaves the checkout flow untouched
- All POST/PUT/DELETE carry a stable `Idempotency-Key` header; auto-retry at the HTTP layer is restricted to idempotent methods (GET/HEAD/OPTIONS) so transient 5xx can't duplicate events or listings
- Event creation is serialised via row-level lock (`select_for_update`) + re-read guard
- Webhook event lookup is O(1) via a cached `ticketswap_event_id → Event` map; webhook position lookup uses a DB filter, not a Python scan
- Webhook deliveries are de-duplicated for 6h by webhook id (or payload hash as fallback)
- `meta_info` is a Pretix TextField — every write goes through `utils.dump_meta` (JSON-serialise) and every read through `utils.ensure_dict`
- Connection status and event lookups are cached to keep admin pages and webhook path snappy

## Requirements

- Pretix >= 2024.7.0
- Python >= 3.9
- A [TicketSwap partnership](https://www.ticketswap.com/partners) with API credentials

## Installation

```bash
# From source
git clone https://github.com/h3x4d3x4/Pretix-TicketSwap.git
cd Pretix-TicketSwap
pip install -e .
```

Then restart Pretix, go to your event's plugin settings, and enable **TicketSwap Integration**.

## Configuration

In your event's admin panel, navigate to **Settings > TicketSwap** and configure:

| Setting | Description | Default |
|---------|-------------|---------|
| **Enable TicketSwap Integration** | Master toggle | Off |
| **API Key** | From your TicketSwap partnership dashboard | — |
| **API Secret** | Keep confidential | — |
| **Webhook Secret** | Used to verify incoming TicketSwap webhooks | — |
| **Auto-enable Resale** | List tickets automatically when orders are paid | On |
| **Maximum Resale Price (%)** | Cap on resale markup (e.g., 120 = 20% above face value) | 120 |

Use the **Test Connection** button to verify credentials before saving.

### Webhook setup

Point TicketSwap's webhook to:

```
https://your-pretix-instance/_ticketswap/webhook/
```

Signatures can be sent either as a bare hex digest or in the `sha256=<hex>` form. The payload must include an `event_id` (your TicketSwap event ID) so the plugin can route it to the correct Pretix event, and ideally an `id` field for replay-dedup.

The plugin handles these event types:
- `ticket.sold` — marks the position as sold
- `ticket.transferred` — updates the barcode (SecureSwap)
- `ticket.cancelled` — marks the listing as cancelled

## Development

### Sandbox mode

Without API credentials, the client runs in sandbox mode with mock responses:

```python
from pretix_ticketswap.ticketswap_api import TicketSwapAPI

api = TicketSwapAPI()  # No credentials = sandbox
result = api.create_event({"name": "Test Event"})
# {'id': 'mock_event_123', 'name': 'Test Event', 'status': 'active', ...}
```

### Running tests

```bash
pip install pytest
pytest pretix_ticketswap/tests/ -v
```

### Code quality

```bash
pip install flake8 isort
flake8 pretix_ticketswap/
isort --check-only pretix_ticketswap/
```

## Project structure

```
pretix_ticketswap/
├── __init__.py              # Version
├── apps.py                  # Django AppConfig + PretixPluginMeta
├── ticketswap_api.py        # API client (shared session, retry, idempotency, SSRF guard)
├── tasks.py                 # Task functions (sync/list/delist + ensure_ticketswap_event)
├── signals.py               # on_commit-deferred signal dispatchers
├── views.py                 # Dashboard, settings, test connection, webhook, manual actions
├── forms.py                 # Settings form (stored-secret aware)
├── urls.py                  # URL routing (5 endpoints)
├── utils.py                 # Meta-info serialisation helpers (ensure_dict / dump_meta)
├── data_shredder.py         # GDPR-compliant data deletion
├── templates/               # Admin dashboard + settings page
├── locale/                  # EN + PT translations (.po + .mo)
└── tests/
    ├── test_api.py          # Legacy API client tests (13)
    ├── test_api_client.py   # Idempotency key, error mapping, signature prefix (10)
    ├── test_forms.py        # Stored-secret UX (5)
    ├── test_signals.py      # Scheduling and dispatch (4)
    └── test_utils.py        # ensure_dict/dump_meta round-trip (10)
```

## Security

- Webhook payloads are verified with HMAC-SHA256 signatures; both `sha256=<hex>` and bare-hex formats are accepted; constant-time comparison
- Webhook replay protection (6h window keyed on webhook `id` or payload hash)
- Payload size limited to 64KB
- No internal error details leaked in responses
- API credentials stored in Pretix's Hierarkey (per-event settings); empty-string credentials force sandbox mode rather than silently authenticating
- SSRF protection on API endpoint construction
- XSS-safe template rendering (user-controlled data uses createTextNode, not innerHTML)
- All admin views require appropriate Pretix permissions
- Idempotency keys on every mutating request prevent duplicates on transient failure retries

## GDPR

The plugin includes a data shredder (`data_shredder.py`) registered with Pretix's GDPR framework. When a data deletion is requested, all TicketSwap metadata is removed from orders and positions. Event-level configuration is preserved since it's not personal data.

## License

[Apache License 2.0](LICENSE)

## Support

- **Plugin issues**: [GitHub Issues](https://github.com/h3x4d3x4/Pretix-TicketSwap/issues)
