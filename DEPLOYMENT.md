# TicketSwap Plugin - Deployment Guide

## Quick Start

### Local Development

```bash
# 1. Navigate to project
cd /Users/andrei/Library/CloudStorage/ProtonDrive-andre.vidal@pm.me-folder/Projects/Suti/PretixPlugin

# 2. Install plugin
pip install -e .

# 3. Start Pretix
cd pretix-test
source venv/bin/activate
python -m pretix runserver 8001

# 4. Access Pretix
open http://localhost:8001
```

### Enable Plugin

1. Go to: `http://localhost:8001/control/event/testorg/testevent/settings/plugins`
2. Find "TicketSwap Integration (v1.0.0)"
3. Click "Enable"
4. Navigate to **Settings** → **TicketSwap**

## Production Deployment

### Step 1: Prepare Environment

```bash
# Install plugin in production Pretix environment
pip install -e /path/to/pretix-ticketswap

# Compile translations
cd pretix_ticketswap/locale/pt/LC_MESSAGES
msgfmt -o django.mo django.po

# Restart Pretix
systemctl restart pretix-web
systemctl restart pretix-worker
```

### Step 2: Obtain TicketSwap Credentials

1. Visit https://partners.ticketswap.com/
2. Contact TicketSwap partnership team
3. Request API access
4. Obtain:
   - API Key
   - API Secret
   - Webhook Secret

### Step 3: Configure Plugin

1. **Disable Sandbox Mode**
   
   Edit `pretix_ticketswap/ticketswap_api.py`:
   ```python
   # Line 45
   SANDBOX_MODE = False  # Change from True to False
   ```

2. **Configure Webhook Secret**
   
   Edit `pretix_ticketswap/views.py`:
   ```python
   # Line 143
   webhook_secret = "your_actual_webhook_secret"  # Replace with real secret
   ```

3. **Enter Credentials in Pretix**
   - Navigate to event settings
   - Go to **Settings** → **TicketSwap** → **Plugin Settings**
   - Enter API Key and Secret
   - Click "Test Connection"
   - Verify success message
   - Enable integration
   - Click "Save"

### Step 4: Configure TicketSwap Webhook

In your TicketSwap partner dashboard:

1. Navigate to webhook settings
2. Set webhook URL: `https://your-pretix-domain.com/ticketswap/webhook/`
3. Set webhook secret (same as in Step 3.2)
4. Enable events:
   - `ticket.sold`
   - `ticket.transferred`
   - `ticket.cancelled`
5. Save webhook configuration

### Step 5: Test Integration

```bash
# 1. Create test event in Pretix
# 2. Verify event created on TicketSwap (check dashboard for Event ID)
# 3. Create test order
# 4. Mark order as paid
# 5. Verify ticket listed on TicketSwap
# 6. Test webhook delivery (check Pretix logs)
```

## Environment Variables (Optional)

For enhanced security, you can use environment variables:

```bash
# In your Pretix environment file
export TICKETSWAP_API_KEY="your_api_key"
export TICKETSWAP_API_SECRET="your_api_secret"
export TICKETSWAP_WEBHOOK_SECRET="your_webhook_secret"
```

Then update code to read from environment:

```python
import os

api_key = os.environ.get('TICKETSWAP_API_KEY')
api_secret = os.environ.get('TICKETSWAP_API_SECRET')
webhook_secret = os.environ.get('TICKETSWAP_WEBHOOK_SECRET')
```

## Monitoring

### Check Logs

```bash
# Pretix logs
tail -f /path/to/pretix/data/logs/pretix.log | grep ticketswap

# Filter for errors
grep -i "error" /path/to/pretix/data/logs/pretix.log | grep ticketswap

# Check webhook deliveries
grep "webhook" /path/to/pretix/data/logs/pretix.log
```

### Monitor Dashboard

- Connection status: Green = OK, Red = Failed
- Statistics: Track tickets listed, sold, transfers
- Recent activity: Monitor operations

## Rollback Plan

If issues occur:

```bash
# 1. Disable plugin in Pretix UI
# Settings → Plugins → TicketSwap Integration → Disable

# 2. Or uninstall completely
pip uninstall pretix-ticketswap

# 3. Restart Pretix
systemctl restart pretix-web
systemctl restart pretix-worker
```

## Security Checklist

- [ ] Sandbox mode disabled in production
- [ ] Real API credentials configured
- [ ] Webhook secret set and matches TicketSwap
- [ ] HTTPS enabled on webhook endpoint
- [ ] Credentials not committed to version control
- [ ] Logs monitored for security issues

## Performance Considerations

- API calls are made synchronously (consider async for high-volume)
- Webhook endpoint should respond quickly (< 5 seconds)
- Consider rate limiting if needed
- Monitor API quota usage

## Support

For deployment issues:
- **Email**: andre.vidal@pm.me
- **Logs**: Check `/path/to/pretix/data/logs/pretix.log`
- **TicketSwap Support**: https://partners.ticketswap.com/

---

**Last Updated**: 2026-01-18
