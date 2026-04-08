# Changelog

All notable changes to the TicketSwap Integration plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
