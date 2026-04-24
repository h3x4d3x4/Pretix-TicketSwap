# Changelog

All notable changes to the TicketSwap Integration plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-04-24

### Fixed
- Signal handlers no longer block the Pretix checkout/payment/cancel flow — API work is deferred via ``transaction.on_commit`` and failures are isolated so an API outage can never roll back an order
- ``meta_info`` (a TextField) was being assigned raw dicts, causing Python-repr strings to hit the DB and crash subsequent reads — all writers now serialise via the new ``dump_meta`` helper
- Event-creation race condition: ``ensure_ticketswap_event`` now takes a row-level lock so two concurrent orders can't double-create the TicketSwap event
- Form validation no longer forces the admin to re-type the API secret every time an unrelated setting is toggled — stored values count as present
- Webhook event lookup is now O(1) via a cached ``ticketswap_event_id → Event`` map, not an O(N) scan of every event with the plugin enabled
- Webhook ticket-id → position lookup uses a DB filter instead of iterating every position on the event
- Webhook signature verification accepts both ``sha256=<hex>`` and bare-hex formats
- Auto-retry is restricted to idempotent HTTP methods; POST/PUT/DELETE carry a stable ``Idempotency-Key`` header instead, so transient 5xx can no longer duplicate events or listings
- Canceled positions and addon positions are excluded from automatic resale listing
- Better error classification: 404 → ``TicketSwapNotFoundError``, 429 → ``TicketSwapRateLimitError``, 403 → ``TicketSwapAuthError``

### Added
- Webhook replay protection: each delivery's ``id`` (or payload signature hash) is remembered for 6h; duplicates short-circuit to 200 without re-processing
- ``ticketswap_max_resale_price_percent`` is now actually sent to TicketSwap on listing, alongside attendee name/email, barcode, and item/variation details
- Admin ``/ticketswap/order-action/`` endpoint for manually re-running sync/list/delist on a specific order
- ``ensure_ticketswap_event`` helper (used by signals, form-save path, and manual actions) — single source of truth for event creation
- Correlation fields (``event=slug order=CODE pos=ID``) in every log line so an order can be traced end-to-end
- Test coverage: +29 tests (42 total) across utils, forms, signals, and the API client's idempotency/error mapping

### Changed
- Webhook URL changed from ``/ticketswap/webhook/`` to ``/_ticketswap/webhook/`` to match Pretix core plugin convention (underscore-prefix namespace)
- Dashboard stats query filters at the DB layer and iterates with chunking, so events with millions of positions don't load them all into memory
- Credentials check is stricter: any half-configured event (key without secret or vice versa) stays in sandbox mode instead of silently accepting

### Security
- ``TicketSwapAPI()`` with empty-string credentials now explicitly falls back to sandbox (prevents partial misconfigurations from masquerading as live)
- Negative webhook event-lookup cache prevents a flood of bad ``event_id`` values from hammering the DB

## [1.0.1] - 2026-04-08

### Fixed
- Fix plugin entry point so Pretix correctly discovers and loads the plugin
- Fix password fields erasing stored API credentials when form is re-saved
- Fix single position API failure silently skipping all remaining positions
- Fix form_valid using blank form value instead of stored secret for API client
- Add webhook event_id type validation

### Changed
- Dashboard stats now computed from real position data instead of hardcoded zeros
- Remove non-functional disabled buttons from dashboard
- Extract shared `ensure_dict` helper to `utils.py` (was duplicated)
- Sync locale .po/.mo files with current code strings
- Remove redundant documentation files, clean up repo for review

## [1.0.0] - 2026-01-18

### Added
- Event synchronization — automatic event creation on TicketSwap when integration is enabled
- Automatic ticket listing when orders are paid
- Automatic ticket delisting when orders are cancelled
- SecureSwap support — barcode invalidation and regeneration on ticket transfer
- Webhook endpoint with HMAC-SHA256 signature verification
- Admin dashboard with connection status and event sync overview
- Settings page with live connection testing
- Sandbox mode with mock API responses for development
- GDPR-compliant data shredder (data export + deletion)
- Multi-language support (English, Portuguese)

### Technical
- Compatible with Pretix >= 2024.7.0
- Python >= 3.9
- Connection pooling with retry (urllib3/requests)
- SSRF protection on API endpoint construction
- Per-position error isolation in listing/delisting operations
