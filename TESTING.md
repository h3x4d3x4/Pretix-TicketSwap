# Quick Start Guide - Testing the Plugin

## Prerequisites

You'll need a Pretix development environment. If you don't have one, here's the quickest way:

### Option 1: Docker (Recommended for Testing)
```bash
# Pull Pretix Docker image
docker pull pretix/standalone:stable

# Run Pretix
docker run -d --name pretix-test -p 8000:80 pretix/standalone:stable
```

### Option 2: Local Development
```bash
# Install Pretix (requires Python 3.9+)
pip install pretix

# Initialize database
python -m pretix migrate

# Create superuser
python -m pretix createsuperuser
```

---

## Installing the Plugin

### Step 1: Install the Plugin

```bash
cd /Users/andrei/Library/CloudStorage/ProtonDrive-andre.vidal@pm.me-folder/Projects/Suti/PretixPlugin

# Install in development mode
pip install -e .
```

### Step 2: Restart Pretix

If using Docker:
```bash
docker restart pretix-test
```

If running locally:
```bash
# Stop and restart your Pretix server
```

---

## Testing the Plugin

### 1. Access Pretix Admin

Open your browser and go to:
- Docker: `http://localhost:8000`
- Local: `http://localhost:8000` (or your configured port)

### 2. Create a Test Event

1. Log in with your admin credentials
2. Create a new organizer (if needed)
3. Create a new event

### 3. Enable TicketSwap Plugin

1. Go to your event settings
2. Navigate to **Plugins**
3. Find "TicketSwap Integration"
4. Enable it
5. Click **Save**

### 4. Configure TicketSwap Settings

1. In event settings, you should now see **"TicketSwap"** in the navigation
2. Click on it
3. You'll see the settings page with:
   - Sandbox mode notification (since no credentials are configured)
   - Configuration form
   - Help documentation

### 5. Test Sandbox Mode

**Without API credentials:**
1. Check "Enable TicketSwap Integration"
2. Leave API Key and Secret empty
3. Click **Save**
4. You should see a validation error requiring credentials

**With mock credentials (for testing):**
1. Check "Enable TicketSwap Integration"
2. Enter any text in API Key (e.g., "test_key")
3. Enter any text in API Secret (e.g., "test_secret")
4. Click **Save**
5. The plugin will run in sandbox mode and show success message

### 6. Create Test Orders

1. Go to your event's public page
2. Create a test order
3. Mark it as paid
4. Check Pretix logs to see TicketSwap sync activity

**Expected log output:**
```
[SANDBOX] POST events - Data: {'name': 'Your Event', ...}
Order placed for event your-event: ABC12
Created TicketSwap event: mock_event_123
```

---

## What to Look For

### ✅ Settings Page Should Show:
- Sandbox mode alert (blue info box)
- Connection status (not configured / connected / failed)
- Configuration form with all fields
- Help documentation panel

### ✅ When Saving Settings:
- Form validation works
- Success/error messages appear
- Settings are persisted

### ✅ When Creating Orders:
- No errors in Pretix logs
- Sandbox mode logs appear
- Order meta_info contains TicketSwap data

---

## Viewing Logs

### Docker:
```bash
docker logs -f pretix-test
```

### Local:
Check your Pretix log file (usually in `data/logs/`)

Look for lines containing:
- `[SANDBOX]` - Sandbox mode API calls
- `TicketSwap` - Plugin activity
- `Order placed` - Order sync events

---

## Screenshots to Take

When testing, capture:
1. Plugin list showing TicketSwap enabled
2. TicketSwap settings page (empty state)
3. TicketSwap settings page (with sandbox mode)
4. Success message after saving
5. Event navigation showing TicketSwap link

---

## Troubleshooting

### Plugin Not Appearing
```bash
# Verify installation
pip list | grep pretix-ticketswap

# Should show: pretix-ticketswap 1.0.0
```

### Settings Page 404
- Check that plugin is enabled for the event
- Verify URL pattern is correct
- Check Pretix logs for routing errors

### No Logs Appearing
- Ensure logging level is set to INFO or DEBUG
- Check that signal handlers are being called
- Verify plugin is properly loaded

---

## Next Steps After Testing

1. **Test with Real API Credentials** (when available)
   - Contact TicketSwap for partnership
   - Enter real credentials
   - Test live API integration

2. **Test Full Order Lifecycle**
   - Create order → Check sync
   - Pay order → Check ticket listing
   - Cancel order → Check delisting

3. **Test Data Shredder**
   - Go to event settings → Data privacy
   - Find TicketSwap data shredder
   - Test data export and deletion

---

## Ready to Test!

The plugin is fully functional in sandbox mode. You can test all features without needing TicketSwap API credentials.

**Start with:** Installing the plugin and accessing the settings page to see the professional UI! 🎉
