# TicketSwap Plugin - Installation Guide

## Quick Installation

### 1. Install the Plugin

```bash
# From the plugin directory
cd /path/to/pretix-ticketswap
pip install -e .
```

### 2. Restart Pretix

```bash
# If using systemd
systemctl restart pretix-web
systemctl restart pretix-worker

# Or if running manually
# Stop the server (Ctrl+C) and restart:
python -m pretix runserver
```

### 3. Enable in Pretix UI

1. Log in to Pretix admin
2. Navigate to your event
3. Go to **Settings** → **Plugins**
4. Find "TicketSwap Integration (v1.0.0)"
5. Click **Enable**

### 4. Access the Plugin

- **Dashboard**: `http://your-domain/control/event/{organizer}/{event}/ticketswap/`
- **Settings**: `http://your-domain/control/event/{organizer}/{event}/ticketswap/settings/`

## Configuration

### Enter API Credentials

1. Go to **Settings** → **TicketSwap** → **Plugin Settings**
2. Enter your TicketSwap API Key
3. Enter your TicketSwap API Secret
4. Click **Test Connection** to verify
5. Configure options:
   - Enable TicketSwap Integration
   - Auto-enable Resale (default: Yes)
   - Maximum Resale Price % (default: 120%)
6. Click **Save**

## Files to Include When Sharing

```
pretix-ticketswap/
├── pretix_ticketswap/          # Plugin source code
├── setup.py                     # Installation config
├── README.md                    # Full documentation
├── CHANGELOG.md                 # Version history
├── PROJECT_SUMMARY.md           # Complete overview
├── DEPLOYMENT.md                # Production deployment
└── LICENSE                      # Apache 2.0
```

## For Production Deployment

See **DEPLOYMENT.md** for detailed production setup instructions.

## Support

- **Email**: andre.vidal@pm.me
- **TicketSwap Partnership**: https://partners.ticketswap.com/
