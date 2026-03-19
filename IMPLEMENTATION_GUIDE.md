# Implementation Guide - Pretix-TicketSwap Plugin

## Quick Reference for Developers

This guide provides step-by-step instructions for common implementation tasks.

---

## Table of Contents

1. [Initial Setup](#initial-setup)
2. [Understanding the Codebase](#understanding-the-codebase)
3. [Adding Features](#adding-features)
4. [Testing](#testing)
5. [Deployment](#deployment)

---

## Initial Setup

### Step 1: Clone and Install

```bash
# Navigate to project
cd /Users/andrei/Library/CloudStorage/ProtonDrive-andre.vidal@pm.me-folder/Projects/Suti/PretixPlugin

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install plugin
pip install -e .

# Install dev dependencies
pip install pytest flake8 isort
```

### Step 2: Understand the Structure

```
PretixPlugin/
├── pretix_ticketswap/       # Main plugin code
│   ├── __init__.py          # START HERE - Plugin config
│   ├── signals.py           # Event handlers
│   ├── ticketswap_api.py    # API client
│   ├── forms.py             # Settings form
│   ├── views.py             # Settings view
│   └── ...
├── setup.py                 # Package configuration
├── README.md                # User documentation
├── CONTRIBUTING.md          # Developer guide
└── TESTING.md               # Testing instructions
```

### Step 3: Run Tests

```bash
# Verify everything works
pytest pretix_ticketswap/tests/

# Should see: All tests passed
```

---

## Understanding the Codebase

### Entry Point: `__init__.py`

**What it does:** Defines plugin metadata and registers with Pretix.

**Key class:**
```python
class TicketSwapApp(AppConfig):
    class PretixPluginMeta:
        name = "TicketSwap Integration"
        version = "1.0.0"
        category = "INTEGRATION"
```

**Important:** The `ready()` method imports signals to register handlers.

---

### Signal Handlers: `signals.py`

**What it does:** Listens to Pretix events and triggers TicketSwap actions.

**Flow:**
```
Order Placed → handle_order_placed() → Sync event to TicketSwap
Order Paid → handle_order_paid() → List tickets
Order Canceled → handle_order_canceled() → Delist tickets
```

**Example:**
```python
@receiver(order_paid, dispatch_uid="ticketswap_order_paid")
def handle_order_paid(sender, **kwargs):
    order = kwargs.get("order")
    event = sender
    
    # Check if enabled
    if not event.settings.get("ticketswap_enabled"):
        return
    
    # List tickets on TicketSwap
    # ...
```

---

### API Client: `ticketswap_api.py`

**What it does:** Handles all TicketSwap API communication.

**Key features:**
- **Sandbox mode:** Automatic when no credentials
- **Mock responses:** For testing without API
- **Error handling:** Specific exceptions for different errors

**Example usage:**
```python
# Initialize
api = TicketSwapAPI(api_key, api_secret)

# Create event
event = api.create_event({
    "name": "My Event",
    "date": "2026-06-01T20:00:00Z"
})

# List ticket
ticket = api.list_ticket({
    "event_id": event["id"],
    "price": 50.00
})
```

---

### Settings: `forms.py` + `views.py`

**forms.py** - Defines settings form:
```python
class TicketSwapSettingsForm(forms.Form):
    ticketswap_enabled = forms.BooleanField(...)
    ticketswap_api_key = forms.CharField(...)
    # ...
```

**views.py** - Handles form display and submission:
```python
class TicketSwapSettingsView(FormView):
    def form_valid(self, form):
        # Save settings
        # Create event if first time
        # Show success message
```

---

## Adding Features

### Example: Add Webhook Handler

**Step 1:** Create webhook view in `views.py`

```python
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseForbidden

@csrf_exempt
def webhook_handler(request):
    """Handle TicketSwap webhooks."""
    if request.method != "POST":
        return HttpResponseForbidden()
    
    # Get signature from headers
    signature = request.META.get("HTTP_X_TICKETSWAP_SIGNATURE")
    payload = request.body
    
    # Verify signature
    api = TicketSwapAPI()
    secret = request.event.settings.get("ticketswap_webhook_secret")
    
    if not api.verify_webhook_signature(payload, signature, secret):
        return HttpResponseForbidden()
    
    # Process webhook
    data = json.loads(payload)
    event_type = data.get("event")
    
    if event_type == "ticket.sold":
        # Handle ticket sold
        pass
    
    return HttpResponse(status=200)
```

**Step 2:** Add URL pattern in `urls.py`

```python
urlpatterns = [
    path("settings/", TicketSwapSettingsView.as_view(), name="settings"),
    path("webhook/", webhook_handler, name="webhook"),  # NEW
]
```

**Step 3:** Add webhook secret to settings form

```python
# In forms.py
ticketswap_webhook_secret = forms.CharField(
    label=_("Webhook Secret"),
    required=False,
    widget=forms.PasswordInput()
)
```

**Step 4:** Test

```python
# In tests/test_webhooks.py
def test_webhook_verification():
    # Test valid signature
    # Test invalid signature
    # Test event processing
```

---

### Example: Add Custom Pricing Rules

**Step 1:** Add setting

```python
# In forms.py
ticketswap_custom_pricing = forms.BooleanField(
    label=_("Use Custom Pricing"),
    required=False
)
```

**Step 2:** Modify ticket listing logic

```python
# In signals.py, handle_order_paid()
max_price_percent = event.settings.get("ticketswap_max_resale_price_percent", 120)

if event.settings.get("ticketswap_custom_pricing"):
    # Apply custom pricing logic
    max_price = position.price * (max_price_percent / 100)
else:
    # Use default
    max_price = position.price
```

**Step 3:** Update API call

```python
ticket_data = {
    "event_id": ticketswap_event_id,
    "price": float(position.price),
    "max_price": float(max_price),  # NEW
    "currency": event.currency,
}
```

---

## Testing

### Writing Unit Tests

**Location:** `pretix_ticketswap/tests/`

**Template:**
```python
from django.test import TestCase
from ..ticketswap_api import TicketSwapAPI

class MyFeatureTestCase(TestCase):
    def setUp(self):
        """Setup test data."""
        self.api = TicketSwapAPI()
    
    def test_my_feature(self):
        """Test my feature works correctly."""
        result = self.api.my_method({"data": "test"})
        self.assertEqual(result["status"], "success")
```

### Running Tests

```bash
# All tests
pytest

# Specific file
pytest pretix_ticketswap/tests/test_api.py

# Specific test
pytest pretix_ticketswap/tests/test_api.py::TicketSwapAPITestCase::test_sandbox_mode

# With coverage
pytest --cov=pretix_ticketswap --cov-report=html
```

### Manual Testing

1. Install in Pretix dev environment
2. Enable plugin for test event
3. Configure settings (sandbox mode)
4. Create orders and verify sync
5. Check logs for activity

---

## Deployment

### Pre-Deployment Checklist

- [ ] All tests pass
- [ ] Code style checks pass (`flake8`)
- [ ] Imports sorted (`isort`)
- [ ] Documentation updated
- [ ] Translations complete
- [ ] Version bumped in `__init__.py`

### Building Package

```bash
# Clean previous builds
rm -rf build/ dist/ *.egg-info

# Build
python setup.py sdist bdist_wheel

# Verify
twine check dist/*
```

### Publishing to PyPI

```bash
# Test PyPI first
twine upload --repository testpypi dist/*

# Production
twine upload dist/*
```

### Installing in Production

```bash
# From PyPI
pip install pretix-ticketswap

# From local build
pip install dist/pretix_ticketswap-1.0.0-py3-none-any.whl

# Restart Pretix
systemctl restart pretix
```

---

## Troubleshooting

### Plugin Not Loading

**Check:**
1. Plugin installed: `pip list | grep pretix-ticketswap`
2. Entry point correct in `setup.py`
3. Pretix restarted after installation

**Fix:**
```bash
pip uninstall pretix-ticketswap
pip install -e .
# Restart Pretix
```

### Settings Page Not Showing

**Check:**
1. Plugin enabled for event
2. URL pattern correct
3. View has proper permissions

**Debug:**
```python
# Add to views.py
import logging
logger = logging.getLogger(__name__)
logger.debug("Settings view accessed")
```

### API Calls Failing

**Check:**
1. Credentials correct
2. Network connectivity
3. Sandbox mode vs live mode

**Debug:**
```python
# In ticketswap_api.py
logger.info(f"API request: {method} {endpoint}")
logger.info(f"Response: {response.text}")
```

---

## Quick Commands Reference

```bash
# Development
pip install -e .                    # Install in dev mode
pytest                              # Run tests
flake8 pretix_ticketswap/          # Check code style
isort pretix_ticketswap/           # Sort imports

# Building
python setup.py sdist bdist_wheel  # Build package
twine check dist/*                  # Verify package

# Deployment
pip install pretix-ticketswap      # Install from PyPI
pip install dist/*.whl              # Install from local build

# Debugging
python -m pdb script.py            # Debug Python
pytest -v                           # Verbose test output
pytest --pdb                        # Drop into debugger on failure
```

---

## Next Steps

1. **Read the code** - Start with `__init__.py`, then `signals.py`
2. **Run tests** - Understand what's being tested
3. **Make changes** - Start small, test often
4. **Read CONTRIBUTING.md** - Detailed architecture info
5. **Ask questions** - andre.vidal@pm.me

**Happy coding!** 🚀
