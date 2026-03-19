# Pretix-TicketSwap Integration Plugin

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Pretix](https://img.shields.io/badge/pretix-2024.7.0+-green.svg)](https://pretix.eu/)

A professional Pretix plugin that integrates with TicketSwap's secondary ticket marketplace, enabling secure and fair ticket resale through TicketSwap's SecureSwap technology.

## Features

✨ **Automatic Event Synchronization** - Your Pretix events are automatically synced to TicketSwap  
🔒 **SecureSwap Integration** - Ticket invalidation and regeneration for secure resale  
🎫 **Automatic Ticket Listing** - Tickets are listed for resale when orders are paid  
🗑️ **Automatic Delisting** - Tickets are removed when orders are canceled  
🔐 **GDPR Compliant** - Full data shredder for privacy compliance  
🌍 **Multi-language Support** - English, German, and Portuguese translations  
🧪 **Sandbox Mode** - Test the plugin without API credentials

## Requirements

- Pretix >= 2024.7.0
- Python >= 3.9
- TicketSwap partnership and API credentials

## Installation

### From PyPI (when published)

```bash
pip install pretix-ticketswap
```

### From Source

```bash
git clone https://github.com/yourusername/pretix-ticketswap.git
cd pretix-ticketswap
pip install -e .
```

### In Pretix

1. Install the plugin in your Pretix environment
2. Restart your Pretix server
3. Navigate to your event settings
4. Find "TicketSwap" in the plugins section
5. Enable the plugin

## Configuration

### 1. Get TicketSwap API Credentials

Before using this plugin, you need to establish a partnership with TicketSwap:

1. Visit [TicketSwap Partners](https://www.ticketswap.com/partners)
2. Contact their partnership team
3. Request API access
4. Obtain your API key and secret

### 2. Configure the Plugin

1. Go to your event in Pretix admin
2. Navigate to **Settings** → **TicketSwap**
3. Enter your API credentials:
   - **API Key**: Your TicketSwap API key
   - **API Secret**: Your TicketSwap API secret
4. Configure options:
   - **Enable TicketSwap Integration**: Turn on/off the integration
   - **Auto-enable Resale**: Automatically list tickets when orders are paid
   - **Maximum Resale Price**: Set the max markup percentage (default: 120%)
5. Click **Save**

The plugin will automatically create your event on TicketSwap and display the Event ID.

## How It Works

### Order Lifecycle

1. **Order Placed** → Event is synced to TicketSwap (if not already)
2. **Order Paid** → Tickets are listed for resale on TicketSwap
3. **Order Canceled** → Tickets are removed from TicketSwap

### SecureSwap Process

When a ticket is resold through TicketSwap:

1. Original ticket is invalidated
2. New ticket is generated with updated buyer details
3. New barcode is created
4. Pretix is notified of the change (via webhooks)

## Development

### Setup Development Environment

```bash
# Clone the repository
git clone https://github.com/yourusername/pretix-ticketswap.git
cd pretix-ticketswap

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .
pip install pytest flake8 isort

# Run tests
pytest

# Check code quality
flake8 pretix_ticketswap/
isort --check-only pretix_ticketswap/
```

### Sandbox Mode

The plugin includes a sandbox mode for development and testing without API credentials:

```python
from pretix_ticketswap.ticketswap_api import TicketSwapAPI

# Initialize in sandbox mode (no credentials)
api = TicketSwapAPI()

# All API calls will return mock responses
result = api.create_event({"name": "Test Event"})
print(result)  # {'id': 'mock_event_123', 'name': 'Test Event', ...}
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=pretix_ticketswap --cov-report=html

# Run specific test file
pytest pretix_ticketswap/tests/test_api.py
```

## API Reference

### TicketSwapAPI Client

```python
from pretix_ticketswap.ticketswap_api import TicketSwapAPI

# Initialize with credentials
api = TicketSwapAPI(api_key="your_key", api_secret="your_secret")

# Create event
event = api.create_event({
    "name": "My Event",
    "date": "2026-06-01T20:00:00Z",
    "location": "Venue Name"
})

# List ticket for resale
ticket = api.list_ticket({
    "event_id": event["id"],
    "price": 50.00,
    "currency": "EUR"
})

# Execute SecureSwap
new_ticket = api.secureswap_ticket(
    old_ticket_id="ticket_123",
    new_buyer_data={"name": "John Doe", "email": "john@example.com"}
)

# Test connection
is_connected = api.test_connection()
```

## Troubleshooting

### Plugin Not Appearing

- Ensure the plugin is installed: `pip list | grep pretix-ticketswap`
- Restart your Pretix server
- Check Pretix logs for errors

### API Connection Failed

- Verify your API credentials are correct
- Check that you have an active TicketSwap partnership
- Ensure your server can reach `api.ticketswap.com`
- Check Pretix logs for detailed error messages

### Tickets Not Syncing

- Verify the plugin is enabled for your event
- Check that API credentials are configured
- Review the Pretix logs for sync errors
- Ensure "Auto-enable Resale" is turned on (if desired)

## Support

For technical support or questions:

- **Email**: andre.vidal@pm.me
- **Issues**: [GitHub Issues](https://github.com/yourusername/pretix-ticketswap/issues)

For TicketSwap partnership questions:
- **Website**: [ticketswap.com/partners](https://www.ticketswap.com/partners)

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

Please ensure:
- All tests pass (`pytest`)
- Code follows style guidelines (`flake8`, `isort`)
- New features include tests
- Documentation is updated

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Pretix](https://pretix.eu/) - The amazing ticketing platform
- [TicketSwap](https://www.ticketswap.com/) - Secure ticket resale marketplace
- All contributors and users of this plugin

## Changelog

### Version 1.0.0 (2026-01-18)

- Initial release
- Event synchronization to TicketSwap
- Automatic ticket listing on order payment
- Automatic delisting on order cancellation
- SecureSwap integration support
- GDPR-compliant data shredder
- Multi-language support (EN, DE, PT)
- Comprehensive test suite
- Sandbox mode for development

---

Made with ❤️ for the Pretix and TicketSwap communities
