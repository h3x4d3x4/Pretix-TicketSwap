# AI Assistant Context Guide

## For: Claude, ChatGPT, or any AI Assistant

**Purpose:** This document provides complete context for AI assistants to understand and work on this project without prior conversation history.

---

## Project Overview

**Name:** Pretix-TicketSwap Integration Plugin  
**Type:** Django plugin for Pretix ticketing platform  
**Language:** Python 3.9+  
**Status:** Production-ready, fully tested, marketplace-compliant  
**License:** Apache 2.0

**What it does:** Integrates Pretix events with TicketSwap's secondary ticket marketplace for secure ticket resale using SecureSwap technology.

---

## Quick Context

### The Problem
Event organizers using Pretix want to enable secure ticket resale through TicketSwap but have no integration.

### The Solution
This plugin automatically:
1. Syncs Pretix events to TicketSwap
2. Lists tickets for resale when orders are paid
3. Delists tickets when orders are canceled
4. Supports SecureSwap (invalidate old ticket, generate new one)

### Current State
- ✅ Fully implemented and tested
- ✅ Works in sandbox mode (no API credentials needed)
- ✅ GDPR compliant with data shredder
- ✅ Marketplace-ready documentation
- ⏳ Awaiting TicketSwap partnership for live API access

---

## File Structure (What Each File Does)

```
PretixPlugin/
├── pretix_ticketswap/
│   ├── __init__.py              # Plugin registration & metadata
│   ├── signals.py               # Event handlers (order lifecycle)
│   ├── ticketswap_api.py        # API client (with sandbox mode)
│   ├── forms.py                 # Admin settings form
│   ├── views.py                 # Admin settings view
│   ├── urls.py                  # URL routing
│   ├── data_shredder.py         # GDPR data removal
│   ├── templates/               # Django templates
│   ├── locale/                  # Translations (EN ready)
│   └── tests/                   # Unit tests
│
├── README.md                    # User documentation
├── CONTRIBUTING.md              # Developer guide
├── IMPLEMENTATION_GUIDE.md      # Step-by-step tasks
├── TESTING.md                   # Testing instructions
├── PROJECT_HANDOFF.md           # Project overview
├── setup.py                     # Package configuration
└── pretixplugin.toml           # Plugin metadata
```

---

## Key Concepts for AI Assistants

### 1. Pretix Plugin Architecture

Pretix plugins are Django apps that:
- Register via entry points in `setup.py`
- Use Django signals to react to events
- Store settings in `event.settings`
- Follow specific marketplace requirements

**Critical:** Pretix handles URL routing automatically. Plugin URLs are relative, not absolute.

### 2. Sandbox Mode

The API client has **built-in sandbox mode**:
- Activates when no credentials provided
- Returns mock data for all API calls
- Logs with `[SANDBOX]` prefix
- Perfect for testing without TicketSwap partnership

**Location:** `pretix_ticketswap/ticketswap_api.py`

### 3. Signal Handlers

Three main signals handle the order lifecycle:

```python
order_placed → Sync event to TicketSwap
order_paid → List tickets for resale
order_canceled → Delist tickets
```

**Location:** `pretix_ticketswap/signals.py`

**Important:** All signals use `dispatch_uid` to prevent duplicate registration.

### 4. Data Storage

**Event Settings:**
- `ticketswap_enabled` - Boolean
- `ticketswap_api_key` - String
- `ticketswap_api_secret` - String (encrypted by Pretix)
- `ticketswap_event_id` - String (TicketSwap event ID)

**Order/Position Metadata:**
```json
{
  "ticketswap": {
    "event_id": "ts_event_123",
    "ticket_id": "ts_ticket_456",
    "synced": true,
    "listed": true
  }
}
```

---

## Common AI Assistant Tasks

### Task: "Add a new feature"

**Steps:**
1. Read `IMPLEMENTATION_GUIDE.md` for examples
2. Identify which file(s) to modify
3. Add tests in `tests/test_*.py`
4. Update translations in `locale/en/LC_MESSAGES/django.po`
5. Run `pytest` to verify
6. Update documentation

### Task: "Fix a bug"

**Steps:**
1. Read error message/stack trace
2. Locate relevant file (use grep if needed)
3. Check `debugging_report.md` for known issues
4. Fix the bug
5. Add test to prevent regression
6. Run `pytest` to verify

### Task: "Understand the codebase"

**Read in this order:**
1. `PROJECT_HANDOFF.md` - Overview
2. `pretix_ticketswap/__init__.py` - Entry point
3. `pretix_ticketswap/signals.py` - Core logic
4. `pretix_ticketswap/ticketswap_api.py` - API client
5. `CONTRIBUTING.md` - Architecture details

### Task: "Add a setting"

**Example: Add "webhook_url" setting**

1. **Add to form** (`forms.py`):
```python
ticketswap_webhook_url = forms.URLField(
    label=_("Webhook URL"),
    required=False,
)
```

2. **Add to view** (`views.py`):
```python
# In get_form_kwargs()
"ticketswap_webhook_url": self.request.event.settings.get(
    "ticketswap_webhook_url", ""
),
```

3. **Add translation** (`locale/en/LC_MESSAGES/django.po`):
```
msgid "Webhook URL"
msgstr ""
```

4. **Use in code**:
```python
webhook_url = event.settings.get("ticketswap_webhook_url")
```

---

## Code Patterns to Follow

### Error Handling
```python
try:
    api = TicketSwapAPI(api_key, api_secret)
    result = api.create_event(data)
except TicketSwapAPIError as e:
    logger.error(f"API error: {e}")
    # Handle gracefully
```

### Logging
```python
import logging
logger = logging.getLogger(__name__)

logger.info("Normal operation")
logger.warning("Potential issue")
logger.error("Error occurred")
```

### Translations
```python
from django.utils.translation import gettext_lazy as _

message = _("User-facing text")
```

### Signal Handlers
```python
@receiver(signal_name, dispatch_uid="ticketswap_unique_id")
def handler(sender, **kwargs):
    # Check if enabled
    if not sender.settings.get("ticketswap_enabled"):
        return
    # Your logic
```

---

## Testing

### Run Tests
```bash
pytest                          # All tests
pytest -v                       # Verbose
pytest --cov=pretix_ticketswap  # With coverage
```

### Write Tests
```python
from django.test import TestCase

class MyTestCase(TestCase):
    def test_feature(self):
        # Arrange
        api = TicketSwapAPI()
        
        # Act
        result = api.method()
        
        # Assert
        self.assertEqual(result["status"], "success")
```

---

## Important Files for AI Context

### Always Check These First

1. **`task.md`** - Current project status and checklist
2. **`implementation_plan.md`** - Original design decisions
3. **`debugging_report.md`** - Known bugs and fixes
4. **`PROJECT_HANDOFF.md`** - Quick project overview

### For Understanding Code

1. **`CONTRIBUTING.md`** - Architecture and patterns
2. **`IMPLEMENTATION_GUIDE.md`** - Common tasks
3. **`pretix_ticketswap/__init__.py`** - Plugin config
4. **`pretix_ticketswap/signals.py`** - Core logic

---

## Common Pitfalls (Avoid These!)

### ❌ Don't: Use absolute URLs in `urls.py`
```python
# WRONG
path("control/event/<organizer>/<event>/ticketswap/settings/", ...)
```

### ✅ Do: Use relative URLs
```python
# CORRECT
path("settings/", ...)
```

### ❌ Don't: Forget dispatch_uid on signals
```python
# WRONG
@receiver(order_placed)
```

### ✅ Do: Always include dispatch_uid
```python
# CORRECT
@receiver(order_placed, dispatch_uid="ticketswap_order_placed")
```

### ❌ Don't: Assume meta_info exists
```python
# WRONG
order.meta_info["ticketswap"] = {}
```

### ✅ Do: Check and initialize
```python
# CORRECT
if not order.meta_info:
    order.meta_info = {}
order.meta_info.setdefault("ticketswap", {})
```

### ❌ Don't: Catch ValidationError in form clean()
```python
# WRONG
except Exception as e:
    raise forms.ValidationError(...)
```

### ✅ Do: Re-raise ValidationError
```python
# CORRECT
except forms.ValidationError:
    raise
except Exception as e:
    raise forms.ValidationError(...)
```

---

## Debugging Tips for AI Assistants

### Check Syntax
```bash
python3 -m py_compile pretix_ticketswap/*.py
```

### Check Code Style
```bash
flake8 pretix_ticketswap/
```

### Check Imports
```bash
isort --check-only pretix_ticketswap/
```

### View Logs
Look for:
- `[SANDBOX]` - Sandbox mode activity
- `TicketSwap` - Plugin activity
- `ERROR` - Errors to fix

---

## Quick Reference Commands

```bash
# Install
pip install -e .

# Test
pytest

# Build
python setup.py sdist bdist_wheel

# Check quality
flake8 pretix_ticketswap/
isort pretix_ticketswap/

# Clean
find . -name "*.pyc" -delete
find . -name "__pycache__" -delete
```

---

## Project History (Bugs Fixed)

### First Pass
1. Missing data shredder registration
2. Order meta_info initialization bug

### Second Pass
3. Incorrect URL pattern (had absolute path)
4. Duplicate translation string
5. Unused import in API client

### Third Pass
6. JSON import placement in data shredder
7. Form validation exception handling

**All bugs documented in:** `debugging_report.md` and `second_pass_debugging.md`

---

## What's NOT Implemented (Future Work)

- [ ] Real TicketSwap API integration (needs partnership)
- [ ] Webhook endpoint for TicketSwap callbacks
- [ ] German translation
- [ ] Portuguese translation
- [ ] Advanced pricing rules
- [ ] Bulk operations
- [ ] Analytics dashboard

---

## Critical Context for AI Assistants

### TicketSwap Partnership Required

**Important:** The live TicketSwap API requires a formal partnership. Without it:
- Plugin works in sandbox mode only
- All API calls return mock data
- No real tickets are listed

**To get partnership:**
1. Contact https://www.ticketswap.com/partners
2. Establish partnership agreement
3. Obtain API credentials
4. Get SecureSwap API documentation

### Pretix Marketplace Requirements

Plugin must meet these requirements:
- ✅ Proper licensing (Apache 2.0)
- ✅ Code quality (flake8, isort)
- ✅ Tests (pytest)
- ✅ Documentation (comprehensive)
- ✅ GDPR compliance (data shredder)
- ✅ Internationalization (gettext)
- ✅ Isolation (dispatch_uid, namespaced settings)

**All requirements met!**

---

## How to Help as an AI Assistant

### When User Asks to Add Feature

1. **Understand the request** - Ask clarifying questions
2. **Check existing code** - Look for similar patterns
3. **Read relevant docs** - IMPLEMENTATION_GUIDE.md
4. **Propose approach** - Explain what you'll do
5. **Implement** - Follow existing patterns
6. **Test** - Write tests, run pytest
7. **Document** - Update relevant docs

### When User Reports Bug

1. **Reproduce** - Understand the issue
2. **Locate** - Find relevant code
3. **Check history** - Read debugging_report.md
4. **Fix** - Implement solution
5. **Test** - Prevent regression
6. **Document** - Add to debugging notes

### When User Asks "How does X work?"

1. **Read the code** - Understand it first
2. **Check docs** - See if already documented
3. **Explain clearly** - Use examples
4. **Show code** - Reference specific files/lines
5. **Suggest improvements** - If you see any

---

## Example AI Assistant Workflow

**User:** "Add a feature to limit resale to specific ticket types"

**AI Response:**

1. **Understand:** "I'll add a setting to specify which ticket types can be resold."

2. **Plan:**
   - Add multi-select field to form
   - Update signal handler to check ticket type
   - Add tests
   - Update translations

3. **Implement:**
   ```python
   # In forms.py
   ticketswap_allowed_items = forms.MultipleChoiceField(...)
   
   # In signals.py
   allowed_items = event.settings.get("ticketswap_allowed_items", [])
   if position.item.id not in allowed_items:
       continue  # Skip this ticket
   ```

4. **Test:**
   ```python
   def test_ticket_type_filtering():
       # Test only allowed types are listed
   ```

5. **Document:** Update README.md with new setting

---

## Final Tips for AI Assistants

1. **Always read the code first** - Don't assume, verify
2. **Follow existing patterns** - Consistency is key
3. **Test everything** - Run pytest after changes
4. **Document changes** - Update relevant docs
5. **Check debugging reports** - Learn from past issues
6. **Use sandbox mode** - Test without API credentials
7. **Ask questions** - If unclear, ask the user

---

## Contact & Support

**Original Developer:** Andre Vidal (andre.vidal@pm.me)  
**Documentation:** All .md files in project root  
**Tests:** `pretix_ticketswap/tests/`  
**Issues:** Check debugging_report.md first

---

**You now have complete context to work on this project! Start with PROJECT_HANDOFF.md for overview, then dive into the code.** 🤖
