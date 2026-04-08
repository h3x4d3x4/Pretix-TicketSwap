# Contributing

## Setup

```bash
git clone https://github.com/h3x4d3x4/Pretix-TicketSwap.git
cd Pretix-TicketSwap
pip install -e .
pip install pytest flake8 isort
```

## Running tests

```bash
pytest pretix_ticketswap/tests/ -v
```

## Code quality

```bash
flake8 pretix_ticketswap/
isort --check-only pretix_ticketswap/
```

## Architecture

```
pretix_ticketswap/
├── signals.py           # Order lifecycle → dispatches task functions
├── tasks.py             # API operations (sync, list, delist)
├── ticketswap_api.py    # HTTP client (retry, pooling, SSRF guard, sandbox mock)
├── views.py             # Dashboard, settings, test connection, webhook handler
├── forms.py             # Settings form with validation
├── urls.py              # 4 URL routes
├── utils.py             # Shared helpers (ensure_dict)
├── data_shredder.py     # GDPR data export + deletion
├── templates/           # Dashboard + settings UI
├── locale/              # EN + PT translations
└── tests/               # API client test suite
```

## Data flow

```
Order placed  → signals.py → tasks.sync_order_to_ticketswap()
Order paid    → signals.py → tasks.list_tickets_for_order()
Order cancel  → signals.py → tasks.delist_tickets_for_order()

TicketSwap webhook → views.TicketSwapWebhookView
  → ticket.sold         → mark position as sold
  → ticket.transferred  → update barcode (SecureSwap)
  → ticket.cancelled    → mark listing as cancelled
```

## Settings storage

All configuration is stored in Pretix's Hierarkey (per-event encrypted settings), not in environment variables or source code. See the settings page in the Pretix admin.

## Adding a new setting

1. Add the field to `forms.py` (`TicketSwapSettingsForm`)
2. Populate its initial value in `views.py` (`get_form_kwargs`)
3. Add translation strings to `locale/*/LC_MESSAGES/django.po`
4. Run `msgfmt -o django.mo django.po` to compile

## License

Apache License 2.0 — see [LICENSE](LICENSE).
