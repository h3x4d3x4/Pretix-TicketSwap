# Changelog

All notable changes to the TicketSwap Integration plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-01-18

### Added
- Initial release of TicketSwap Integration plugin
- **Dashboard View**: Overview of integration status, statistics, and activity
- **Settings Page**: Configure API credentials and integration options
- **SecureSwap Support**: Automatic ticket invalidation and regeneration
- **Sandbox Mode**: Test plugin without real API credentials
- **API Client**: Full TicketSwap API integration with mock responses
- **Event Synchronization**: Automatic event creation on TicketSwap
- **Automatic Ticket Listing**: List tickets when orders are paid
- **Webhook Verification**: HMAC signature validation for webhooks
- **Multi-language Support**: English and Portuguese translations
- **GDPR Compliance**: Data shredder for privacy compliance
- **Connection Testing**: Test API credentials directly from settings
- **Comprehensive Documentation**: README, API docs, and troubleshooting guide

### Features
- Connection status monitoring with visual indicators
- Statistics tracking (tickets listed, sold, SecureSwap transfers)
- Quick actions panel for common tasks
- Event sync status display
- Configurable auto-enable resale
- Configurable maximum resale price (default: 120%)
- Professional error handling and user feedback
- Extensive logging for debugging

### Technical
- Compatible with Pretix >= 2024.7.0
- Python >= 3.9 required
- Uses Hierarkey for settings storage
- Follows Pretix plugin conventions
- Comprehensive test suite included
- Clean, maintainable code structure

## [Unreleased]

### Planned
- Real-time statistics from TicketSwap API
- Activity log with filtering and search
- Bulk ticket operations
- Advanced webhook handling
- Email notifications for important events
- Export functionality for reports
- Multi-event dashboard view
- Performance optimizations

---

For upgrade instructions and migration guides, see [README.md](README.md).
