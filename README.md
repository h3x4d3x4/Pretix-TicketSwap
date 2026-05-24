# pretix-ticketswap (SecureSwap Integration)

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Pretix 2024.7.0+](https://img.shields.io/badge/pretix-2024.7.0+-green.svg)](https://pretix.eu/)

A Pretix plugin that implements the [TicketSwap SecureSwap secondary-ticketing specification](https://ticketswap.stoplight.io/docs/secondary-ticketing) on the **partner side**. Pretix exposes the endpoints; TicketSwap calls into them to validate, swap, and personalize tickets sold through your events.

> **2.0 is a full rewrite.** The 1.x line was wired against an outbound API that does not exist. See [CHANGELOG.md](CHANGELOG.md) for the migration path.

## How it works

```
TicketSwap                               Your Pretix instance
─────────                                ────────────────────
buyer wants to resell  ──→  GET  /validate?barcode=…
                            POST /swap                  ──→  rotates secret on OrderPosition,
buyer about to pay                                           returns new barcode + signed PDF URL
                            POST /personalize           ──→  applies name to attendee fields,
                                                             regenerates PDF
seller publishes listing ──→ POST   /lock/{ticketId}    ──→  marks position locked
seller cancels listing   ──→ DELETE /lock/{ticketId}    ──→  unlocks
sealed flow              ──→ GET /events, /events/{id},
                             GET /tickets/{order_code}
```

Authentication: TicketSwap sends `Authorization: Bearer <token>`. The token is configured once at the organizer level and shared by every event under that organizer.

## Endpoints exposed

All endpoints are mounted under `/_secureswap/api/<organizer>/`:

| Method        | Path                                       | Purpose                                      |
|---------------|--------------------------------------------|----------------------------------------------|
| GET           | `validate?barcode=…`                       | Confirm eligibility for resale               |
| POST          | `swap`                                     | Cancel old barcode, issue new one + PDF URL  |
| POST          | `personalize`                              | Apply attendee details, regenerate PDF       |
| GET           | `personalization-fields/{barcode}`         | Tell TicketSwap which fields to collect      |
| GET           | `events`                                   | List events (paginated, Sealed Ticketing)    |
| GET           | `events/{id}`                              | Fetch one event                              |
| GET           | `tickets/{uniqueIdentifier}`               | List positions of an order                   |
| POST          | `lock/{ticketId}`                          | Mark a ticket as listed-on-TicketSwap        |
| DELETE        | `lock/{ticketId}`                          | Unmark                                       |

PDFs are served via `/_secureswap/pdf/<token>`, a Django-signed URL with a 24h max-age. The plugin re-renders on every fetch so swapped or personalized tickets always reflect current state.

## Installation

```bash
pip install -e .
```

Then in Pretix: **Event → Settings → Plugins → SecureSwap (TicketSwap) Integration → Enable**.

## Configuration

Two layers:

**Organizer-level** (`Organizer → SecureSwap`):
- Partner Bearer Token — what TicketSwap will send in the `Authorization` header. The form has a one-click rotate button.

**Per-event** (`Event → Settings → SecureSwap`):
| Setting | Default | Purpose |
|---------|---------|---------|
| Enable | Off | Master toggle for this event |
| Require personalization | Off | If on, `/swap` returns `pdf:null` and `/personalize` is expected next |
| Event type | OTHER | Enum from the spec (FESTIVAL/CONCERT/CLUB/…) |
| Venue name/city/country | (inferred from `event.location`) | Used by `/events` GenericEvent shape |
| Barcode rendering type | QR-Code | Returned in ticket listings; chooses how partners render the code |
| Swap available until | (none) | ISO 8601 cut-off for swappability |
| Sealed tickets available at | (none) | If set, declares event as sealed |
| Personalization fields | first_name + last_name | JSON array matching the spec's field schema |
| Excluded item IDs | (none) | Comma-separated Pretix item IDs that may not be resold |

The dashboard shows the partner base URL ready to copy into your TicketSwap partner config.

## Architecture

```
pretix_ticketswap/
├── auth.py                  # Bearer token validation, constant-time compare
├── serializers.py           # UUID5-stable IDs, MoneyString / minor-unit conversions, venue inference
├── personalization.py       # Per-event field schema with validation
├── ticket_ops.py            # find / swap / lock / personalize + eligibility checks
├── pdf.py                   # Pretix renderer integration, signed-URL stream view
├── views.py                 # 9 partner endpoints + admin dashboard + 2 settings pages
├── urls.py                  # Partner / public-PDF / admin route groups
├── forms.py                 # Organizer-token form + per-event form
├── signals.py               # Nav entries + data-shredder registration
├── data_shredder.py         # GDPR export + delete
├── utils.py                 # meta_info serialization helpers
├── templates/               # Dashboard + event settings + organizer settings
└── tests/                   # 77 unit tests
```

Key decisions:
- **Stable UUIDs**: Events, items, venues, and positions get UUID5 IDs derived from `position.pk` / `event.pk` so the same Pretix object always serializes to the same ID, with no extra DB column required.
- **Row-locked mutations**: `swap_barcode`, `lock_position`, `apply_personalization` take `select_for_update` to serialize concurrent partner calls.
- **PDF re-render on every fetch**: `CachedTicket` entries are dropped on swap/personalize so the next fetch reflects current state.
- **Best-effort PDF**: If no PDF ticket output is configured, the plugin returns `pdf: null` (spec-allowed) and logs a warning, instead of failing the swap.
- **No outbound API**: The plugin makes no HTTP calls. Everything is request/response with TicketSwap as the client.

## Tests

```bash
# pretix-test/venv has pretix installed
pretix-test/venv/bin/python3 -m pytest pretix_ticketswap/tests/ -v
```

97 unit tests covering:
- Spec serializer shapes (MoneyString, minor units, ISO 8601, UUID stability, venue inference)
- Bearer auth (extraction, constant-time, UNAUTHORIZED response shape)
- Personalization field validation
- PDF signed-token roundtrip + provider selection
- Form validation for organizer + event settings
- All 9 partner endpoints (auth gating + happy paths + error shapes)
- meta_info round-tripping

For end-to-end verification against the real pretix DB:

```bash
DATA_DIR=$(pwd)/pretix-test/data \
DJANGO_SETTINGS_MODULE=pretix.settings \
pretix-test/venv/bin/python3 scripts/smoke.py
```

Seeds two organizers + events/orders, then exercises every admin page,
every partner endpoint, multi-resale chains, the personalization flow,
cross-organizer isolation, and real PDF rendering — 18 checks total.
Safe to re-run.

## Security

- Bearer-token auth, constant-time comparison
- 64 KB cap on inbound JSON payloads
- Spec-shaped error responses leak no internal details
- SSRF irrelevant — plugin never makes outbound HTTP
- PDF URLs are time-bound (24h) and signed with Django's `TimestampSigner`
- Admin views require Pretix permissions (`can_view_orders`, `can_change_event_settings`, `can_change_organizer_settings`)
- All admin templates use bootstrap fields + CSRF tokens; copy-to-clipboard JS uses `createTextNode`, not innerHTML

## GDPR

`data_shredder.py` is registered with Pretix's GDPR framework. When a deletion is requested:
- Exports all `meta_info.ticketswap` data (including any customer info captured during /swap or /personalize) as a JSON download
- Removes the namespace from every affected order and position via bulk update

Event-level settings (token, venue config, personalization schema) are preserved because they aren't personal data.

## License

[Apache License 2.0](LICENSE)

## Support

- **Plugin issues**: [GitHub Issues](https://github.com/h3x4d3x4/Pretix-TicketSwap/issues)
- **Spec questions**: TicketSwap partnership support
