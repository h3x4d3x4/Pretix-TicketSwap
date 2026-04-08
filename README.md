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

Incoming TicketSwap webhooks are verified via HMAC-SHA256 and routed to the correct Pretix event.

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
- Signal handlers are lightweight dispatchers — all API work lives in `tasks.py` (can be wrapped with `@shared_task` for Celery when needed)
- Connection status is cached (5-min TTL) to avoid API calls on every page load
- `meta_info` is handled safely regardless of whether Pretix stores it as a dict or JSON string
- Idempotency guards prevent duplicate ticket listings if signals fire twice

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
https://your-pretix-instance/ticketswap/webhook/
```

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
├── ticketswap_api.py        # API client (shared session, retry, SSRF guard)
├── tasks.py                 # Task functions (sync, list, delist) — Celery-ready
├── signals.py               # Lightweight signal dispatchers
├── views.py                 # Dashboard, settings, test connection, webhook
├── forms.py                 # Settings form with validation
├── urls.py                  # URL routing (4 endpoints)
├── utils.py                 # Shared helpers (ensure_dict)
├── data_shredder.py         # GDPR-compliant data deletion
├── templates/               # Admin dashboard + settings page
├── locale/                  # EN + PT translations (.po + .mo)
└── tests/
    └── test_api.py          # API client tests (15 test cases)
```

## Security

- Webhook payloads are verified with HMAC-SHA256 signatures
- Payload size limited to 64KB
- No internal error details leaked in responses
- API credentials stored in Pretix's Hierarkey (per-event encrypted settings)
- SSRF protection on API endpoint construction
- XSS-safe template rendering (user-controlled data uses createTextNode, not innerHTML)
- All admin views require appropriate Pretix permissions

## GDPR

The plugin includes a data shredder (`data_shredder.py`) registered with Pretix's GDPR framework. When a data deletion is requested, all TicketSwap metadata is removed from orders and positions. Event-level configuration is preserved since it's not personal data.

## License

[Apache License 2.0](LICENSE)

## Support

- **Plugin issues**: [GitHub Issues](https://github.com/h3x4d3x4/Pretix-TicketSwap/issues)
