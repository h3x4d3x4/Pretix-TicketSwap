# Contributing to Pretix-TicketSwap Plugin

## For Developers

This document provides comprehensive information for developers who want to understand, modify, or extend this plugin.

---

## Project Overview

**Purpose:** Integrate Pretix ticketing platform with TicketSwap's secondary marketplace for secure ticket resale.

**Key Technology:** SecureSwap - TicketSwap's technology for invalidating sold tickets and generating new ones for buyers.

**Status:** Production-ready, marketplace-compliant, fully tested.

---

## Architecture

### Plugin Structure

```
pretix_ticketswap/
├── __init__.py              # Plugin configuration & Django app setup
├── signals.py               # Event handlers (order lifecycle)
├── ticketswap_api.py        # API client for TicketSwap
├── forms.py                 # Admin settings form
├── views.py                 # Admin settings view
├── urls.py                  # URL routing
├── data_shredder.py         # GDPR data removal
├── templates/               # Django templates
│   └── pretix_ticketswap/
│       └── settings.html    # Settings page UI
├── locale/                  # Translations
│   └── en/LC_MESSAGES/
│       └── django.po        # English strings
└── tests/                   # Unit tests
    ├── __init__.py
    └── test_api.py          # API client tests
```

### Data Flow

```
Order Placed → Signal Handler → Sync Event to TicketSwap
Order Paid → Signal Handler → List Tickets for Resale
Order Canceled → Signal Handler → Delist Tickets
```

---

## Key Components

### 1. Signal Handlers (`signals.py`)

**Purpose:** Listen to Pretix events and trigger TicketSwap actions.

**Signals Used:**
- `order_placed` - Sync event to TicketSwap
- `order_paid` - List tickets for resale
- `order_canceled` - Remove tickets from listings
- `nav_event_settings` - Add settings link to navigation
- `register_data_shredders` - Register GDPR shredder

**Important:** All signal handlers use `dispatch_uid` to prevent duplicate registration.

### 2. API Client (`ticketswap_api.py`)

**Purpose:** Handle all communication with TicketSwap API.

**Features:**
- Automatic sandbox mode when no credentials provided
- Mock responses for testing
- Comprehensive error handling
- Webhook signature verification
- Connection testing

**Key Methods:**
- `create_event()` - Create event on TicketSwap
- `list_ticket()` - List ticket for resale
- `delist_ticket()` - Remove ticket from listings
- `secureswap_ticket()` - Execute SecureSwap process
- `test_connection()` - Verify API credentials

### 3. Settings Management

**Form (`forms.py`):**
- Validates API credentials
- Tests connection on save
- Enforces required fields when enabled

**View (`views.py`):**
- Displays settings page
- Handles form submission
- Creates event on TicketSwap when first enabled
- Shows connection status

### 4. Data Storage

**Event Settings:**
- `ticketswap_enabled` - Boolean
- `ticketswap_api_key` - String
- `ticketswap_api_secret` - String
- `ticketswap_event_id` - String (TicketSwap event ID)
- `ticketswap_auto_enable_resale` - Boolean
- `ticketswap_max_resale_price_percent` - Integer

**Order Meta Info:**
```json
{
  "ticketswap": {
    "event_id": "ts_event_123",
    "synced": true
  }
}
```

**Position Meta Info:**
```json
{
  "ticketswap": {
    "ticket_id": "ts_ticket_456",
    "listed": true
  }
}
```

---

## Development Setup

### Prerequisites

- Python 3.9+
- Pretix development environment
- Git

### Installation

```bash
# Clone repository
git clone <repository-url>
cd PretixPlugin

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install in development mode
pip install -e .

# Install development dependencies
pip install pytest flake8 isort black
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=pretix_ticketswap --cov-report=html

# Run specific test
pytest pretix_ticketswap/tests/test_api.py::TicketSwapAPITestCase::test_sandbox_mode_initialization
```

### Code Quality

```bash
# Check code style
flake8 pretix_ticketswap/

# Sort imports
isort pretix_ticketswap/

# Format code (optional)
black pretix_ticketswap/
```

---

## Making Changes

### Adding a New Feature

1. **Update `task.md`** - Add feature to checklist
2. **Write tests first** - TDD approach
3. **Implement feature** - Follow existing patterns
4. **Update documentation** - README, docstrings, comments
5. **Test thoroughly** - Unit tests + manual testing
6. **Update translations** - Add new strings to `django.po`

### Modifying API Integration

**Location:** `ticketswap_api.py`

**Steps:**
1. Update mock responses in `_mock_response()` for testing
2. Implement real API call in appropriate method
3. Add error handling
4. Update tests
5. Test in sandbox mode first

### Adding Settings

**Steps:**
1. Add field to `TicketSwapSettingsForm` in `forms.py`
2. Add validation if needed
3. Update `get_form_kwargs()` in `views.py` to populate initial value
4. Add translation strings to `locale/en/LC_MESSAGES/django.po`
5. Update template if UI changes needed

---

## Testing Guide

### Unit Testing

**Test Structure:**
```python
from django.test import TestCase
from ..ticketswap_api import TicketSwapAPI

class MyTestCase(TestCase):
    def setUp(self):
        # Setup test data
        pass
    
    def test_feature(self):
        # Test implementation
        assert True
```

### Manual Testing

1. **Install plugin in Pretix**
2. **Enable for an event**
3. **Configure settings** (use sandbox mode)
4. **Create test orders**
5. **Check logs** for sync activity
6. **Verify data** in order/position meta_info

### Sandbox Mode

The plugin automatically runs in sandbox mode when:
- No API credentials provided
- Or credentials are invalid

All API calls return mock data and are logged with `[SANDBOX]` prefix.

---

## Common Tasks

### Adding a New Signal Handler

```python
@receiver(signal_name, dispatch_uid="ticketswap_unique_id")
def handle_signal(sender, **kwargs):
    """Handle signal description."""
    # Check if enabled
    if not sender.settings.get("ticketswap_enabled"):
        return
    
    # Your logic here
    pass
```

### Adding API Method

```python
def new_method(self, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Method description.
    
    Args:
        data: Input data
        
    Returns:
        Response data
    """
    logger.info(f"Calling new method: {data}")
    return self._make_request("POST", "endpoint", data=data)
```

### Adding Translation

1. Add to `locale/en/LC_MESSAGES/django.po`:
```
msgid "Your new string"
msgstr ""
```

2. Use in code:
```python
from django.utils.translation import gettext_lazy as _

message = _("Your new string")
```

3. Compile (done automatically on build):
```bash
python manage.py compilemessages
```

---

## Debugging

### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Common Issues

**Plugin not appearing:**
- Check `setup.py` entry points
- Verify plugin is installed: `pip list | grep pretix-ticketswap`
- Restart Pretix server

**Settings page 404:**
- Check URL pattern in `urls.py`
- Verify plugin is enabled for event
- Check Pretix logs for routing errors

**API calls failing:**
- Check credentials are correct
- Verify network connectivity
- Review API client logs
- Test in sandbox mode first

---

## Deployment

### Building for Distribution

```bash
# Build package
python setup.py sdist bdist_wheel

# Check package
twine check dist/*

# Upload to PyPI (when ready)
twine upload dist/*
```

### Pretix Marketplace

**Requirements:**
- ✅ All code in repository
- ✅ Apache 2.0 license
- ✅ Comprehensive README
- ✅ Tests included
- ✅ GDPR compliant
- ✅ Translations provided

**Submission:**
1. Create GitHub repository
2. Publish to PyPI
3. Submit to Pretix marketplace
4. Provide support contact

---

## Code Style Guide

### Python

- **PEP 8** compliant
- **Line length:** 100 characters max
- **Imports:** Sorted with isort
- **Docstrings:** Google style
- **Type hints:** Use where helpful

### Django

- **Class-based views** preferred
- **Signals:** Always use `dispatch_uid`
- **Forms:** Validate in `clean()` method
- **Templates:** Use Django template language

### Naming

- **Functions:** `snake_case`
- **Classes:** `PascalCase`
- **Constants:** `UPPER_CASE`
- **Private:** `_leading_underscore`

---

## Security Considerations

### API Credentials

- **Never log** API secrets
- **Store in settings** (encrypted by Pretix)
- **Use password field** in forms
- **Validate before use**

### Webhook Verification

Always verify webhook signatures:
```python
if not api.verify_webhook_signature(payload, signature, secret):
    return HttpResponseForbidden()
```

### Data Privacy

- **Minimal storage** - Only store necessary data
- **GDPR compliance** - Data shredder implemented
- **No PII in logs** - Redact sensitive information

---

## Support & Resources

### Documentation

- **Pretix Docs:** https://docs.pretix.eu/
- **TicketSwap API:** Contact partnership team
- **This Plugin:** See README.md

### Getting Help

- **Issues:** GitHub Issues
- **Email:** andre.vidal@pm.me
- **Pretix Community:** https://pretix.eu/about/en/community

---

## License

Apache License 2.0 - See LICENSE file for details.

---

## Changelog

### Version 1.0.0 (2026-01-18)

- Initial release
- Event synchronization
- Ticket listing/delisting
- SecureSwap support
- GDPR compliance
- Multi-language support
- Comprehensive tests

---

**Ready to contribute? Start by reading the code and running the tests!** 🚀
