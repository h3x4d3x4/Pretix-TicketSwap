# Changelog

All notable changes to the TicketSwap Integration plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
