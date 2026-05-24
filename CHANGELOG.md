# Changelog

All notable changes to the SecureSwap (TicketSwap) Integration plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-05-24

### Changed — full architectural rewrite

The 1.x line was built against an invented outbound REST API at `api.ticketswap.com/v1/` that does not exist. The actual TicketSwap SecureSwap specification at https://ticketswap.stoplight.io/docs/secondary-ticketing defines the opposite direction: **the ticket provider (Pretix) exposes endpoints and TicketSwap calls them**. The entire integration has been rewritten against the real spec.

### Added
- Full coverage of all 9 SecureSwap endpoints, mounted under `/_secureswap/api/<organizer>/`:
  - `GET  /validate?barcode=…` — eligibility check
  - `POST /swap` — cancel old barcode, issue new one + PDF URL
  - `POST /personalize` — apply attendee details + regenerate PDF
  - `GET  /personalization-fields/{barcode}` — admin-configured field list
  - `GET  /events` (paginated) and `GET /events/{id}` — Sealed Ticketing support
  - `GET  /tickets/{uniqueIdentifier}` — list tickets by order code
  - `POST /lock/{ticketId}` and `DELETE /lock/{ticketId}` — block refunds while listed
- Bearer-token authentication, organizer-scoped, constant-time comparison
- PDF generation via Pretix's configured ticket output provider, served at a signed expiring URL (`/_secureswap/pdf/<token>`, 24h max-age)
- Stable UUID5 identifiers for events, items, venues, and positions so partner-side state correlates across calls
- Per-event configuration UI: enable toggle, personalization fields, venue overrides (city/country), event type, barcode rendering type, swap cut-off, sealed availability
- Organizer-level settings page for the partner token (with one-click rotation)
- 97 unit tests covering serializers, auth, forms, personalization, PDF signing, eligibility, and view shape conformance
- `scripts/smoke.py` — end-to-end smoke test that seeds two organizers + events/orders in the pretix-test DB and exercises every admin page, every partner endpoint, multi-resale chains, the personalization flow, cross-organizer isolation, and real PDF rendering (18 checks, all passing)
- `/validate` now distinguishes `TICKET_ALREADY_SWAPPED` (a known-but-revoked barcode) from `TICKET_NOT_FOUND` (truly unknown), tracked via a per-position `revoked_barcodes` list maintained by `/swap`
- One-time data migration `0001_cleanup_v1_settings` to strip orphan v1 settings from every event on `pretix migrate`

### Removed
- `TicketSwapAPI` outbound client (was wired to a non-existent host)
- `tasks.py` outbound dispatchers (`sync_order_to_ticketswap`, `list_tickets_for_order`, `delist_tickets_for_order`)
- Webhook receiver — the real spec uses no webhooks
- API-key / API-secret / webhook-secret form fields
- "Test Connection" admin button — there is nothing outbound to test
- Auto-enable-resale + max-resale-percent options (those are decided on the TicketSwap side)

### Migration

Anyone upgrading from 1.x:

1. Run `python -m pretix migrate` — a one-shot data migration strips the orphaned v1 settings (`ticketswap_api_key`, `ticketswap_api_secret`, `ticketswap_webhook_secret`, `ticketswap_event_id`, `ticketswap_auto_enable_resale`, `ticketswap_max_resale_price_percent`) from every event with the plugin enabled. Idempotent.
2. Configure the new partner Bearer token at the organizer level: **Organizer → SecureSwap → Generate new token**.
3. Toggle SecureSwap on for each event that should be listable: **Event → Settings → SecureSwap → Enable**.
4. Share the partner base URL (visible on the dashboard) with TicketSwap.

## [1.1.0] - 2026-04-24

Last release of the 1.x line. Historical only — the API client it wraps does not exist.

(Previous changelog entries preserved below for historical reference.)

### Fixed
- Signal handlers no longer block the Pretix checkout/payment/cancel flow
- ``meta_info`` writes serialised via ``dump_meta``
- Event-creation race condition closed with row-level lock
- Form validation accepts blank secret fields when one is already stored
- Webhook event lookup is O(1) via a cached map
- Webhook signature verification accepts both ``sha256=<hex>`` and bare-hex formats
- Auto-retry restricted to idempotent HTTP methods; mutating calls use ``Idempotency-Key``
- Canceled positions and addon positions excluded from listing
- Better error classification: 404 → NotFound, 429 → RateLimit, 403 → Auth

### Added
- Webhook replay protection (6h window)
- Admin manual-action endpoint
- Correlation fields in log lines
- 29 additional tests

## [1.0.1] - 2026-04-08

### Fixed
- Plugin entry point so Pretix discovers and loads the plugin
- Password fields no longer erase stored credentials when form is re-saved
- Single position API failure no longer silently skips remaining positions
- Webhook event_id type validation

### Changed
- Dashboard stats computed from real position data
- Removed non-functional disabled buttons
- Extracted shared ``ensure_dict`` helper

## [1.0.0] - 2026-01-18

Initial release.
