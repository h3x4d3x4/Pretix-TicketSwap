"""Form behaviour: the UX we care about is that admins don't have to
retype the API secret every time they change an unrelated setting.
"""

from types import SimpleNamespace

from ..forms import TicketSwapSettingsForm


class _FakeSettings:
    def __init__(self, data):
        self._data = data

    def get(self, key, as_type=str, default=""):
        val = self._data.get(key, default)
        if as_type is bool:
            return bool(val)
        if as_type is int:
            try:
                return int(val)
            except (TypeError, ValueError):
                return default
        return str(val) if val is not None else default


def _event_with(settings):
    return SimpleNamespace(settings=_FakeSettings(settings))


def test_enabled_with_stored_secret_allows_blank_resubmit():
    """User toggles a flag; secret was already stored; form must validate."""
    event = _event_with({
        "ticketswap_api_key": "stored_key",
        "ticketswap_api_secret": "stored_secret",
    })
    form = TicketSwapSettingsForm(
        data={
            "ticketswap_enabled": "on",
            "ticketswap_api_key": "stored_key",
            "ticketswap_api_secret": "",
            "ticketswap_webhook_secret": "",
            "ticketswap_auto_enable_resale": "on",
            "ticketswap_max_resale_price_percent": "120",
        },
        event=event,
    )
    assert form.is_valid(), form.errors


def test_enabled_with_nothing_stored_requires_secret():
    event = _event_with({})
    form = TicketSwapSettingsForm(
        data={
            "ticketswap_enabled": "on",
            "ticketswap_api_key": "key",
            "ticketswap_api_secret": "",
            "ticketswap_max_resale_price_percent": "120",
        },
        event=event,
    )
    assert not form.is_valid()
    assert "ticketswap_api_secret" in form.errors


def test_disabled_form_never_requires_credentials():
    event = _event_with({})
    form = TicketSwapSettingsForm(
        data={
            "ticketswap_enabled": "",
            "ticketswap_max_resale_price_percent": "120",
        },
        event=event,
    )
    assert form.is_valid(), form.errors


def test_max_resale_price_clamped():
    event = _event_with({})
    form = TicketSwapSettingsForm(
        data={
            "ticketswap_enabled": "",
            "ticketswap_max_resale_price_percent": "200",
        },
        event=event,
    )
    assert not form.is_valid()
    assert "ticketswap_max_resale_price_percent" in form.errors


def test_enabled_with_stored_key_blank_key_in_form():
    """Leaving API key blank but having stored value should pass."""
    event = _event_with({
        "ticketswap_api_key": "stored_key",
        "ticketswap_api_secret": "stored_secret",
    })
    form = TicketSwapSettingsForm(
        data={
            "ticketswap_enabled": "on",
            "ticketswap_api_key": "",
            "ticketswap_api_secret": "",
            "ticketswap_max_resale_price_percent": "120",
        },
        event=event,
    )
    assert form.is_valid(), form.errors
