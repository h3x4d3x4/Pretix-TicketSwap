"""
Django forms for TicketSwap plugin configuration.
"""

from django import forms
from django.utils.translation import gettext_lazy as _


class TicketSwapSettingsForm(forms.Form):
    """Form for configuring TicketSwap integration settings.

    ``event`` is accepted as a kwarg so ``clean()`` can consult the
    already-stored secrets and not force the admin to re-type them
    every time they change an unrelated setting.
    """

    ticketswap_enabled = forms.BooleanField(
        label=_("Enable TicketSwap Integration"),
        help_text=_(
            "Enable automatic synchronization of tickets to TicketSwap for resale"
        ),
        required=False,
    )

    ticketswap_api_key = forms.CharField(
        label=_("API Key"),
        help_text=_(
            "Your TicketSwap API key. Obtain this from your TicketSwap partnership dashboard."
        ),
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "ts_api_key_..."}),
    )

    ticketswap_api_secret = forms.CharField(
        label=_("API Secret"),
        help_text=_(
            "Your TicketSwap API secret. Leave blank to keep the currently stored value."
        ),
        required=False,
        widget=forms.PasswordInput(attrs={"placeholder": "••••••••"}, render_value=False),
    )

    ticketswap_webhook_secret = forms.CharField(
        label=_("Webhook Secret"),
        help_text=_(
            "Secret used to verify incoming webhooks from TicketSwap. "
            "Leave blank to keep the currently stored value."
        ),
        required=False,
        widget=forms.PasswordInput(attrs={"placeholder": "••••••••"}, render_value=False),
    )

    ticketswap_auto_enable_resale = forms.BooleanField(
        label=_("Auto-enable Resale"),
        help_text=_(
            "Automatically list tickets on TicketSwap when orders are paid. "
            "If disabled, tickets must be manually enabled for resale."
        ),
        required=False,
        initial=True,
    )

    ticketswap_max_resale_price_percent = forms.IntegerField(
        label=_("Maximum Resale Price (%)"),
        help_text=_(
            "Maximum percentage above original price for resale (e.g., 120 for 20% markup). "
            "TicketSwap typically enforces a 120% maximum."
        ),
        required=False,
        initial=120,
        min_value=100,
        max_value=150,
        widget=forms.NumberInput(attrs={"placeholder": "120"}),
    )

    def __init__(self, *args, event=None, **kwargs):
        self.event = event
        super().__init__(*args, **kwargs)

    def _stored(self, key):
        if not self.event:
            return ""
        return self.event.settings.get(key, as_type=str, default="") or ""

    def clean(self):
        """Require credentials when enabling, but accept stored values.

        When a password field is left blank, we treat the currently
        stored value as still in effect. Only when enabling with no
        stored-and-no-submitted secret do we error out.
        """
        cleaned_data = super().clean()
        enabled = cleaned_data.get("ticketswap_enabled")
        if not enabled:
            return cleaned_data

        api_key = cleaned_data.get("ticketswap_api_key") or self._stored("ticketswap_api_key")
        api_secret = (
            cleaned_data.get("ticketswap_api_secret")
            or self._stored("ticketswap_api_secret")
        )

        if not api_key:
            self.add_error(
                "ticketswap_api_key",
                _("API Key is required when TicketSwap integration is enabled."),
            )
        if not api_secret:
            self.add_error(
                "ticketswap_api_secret",
                _("API Secret is required when TicketSwap integration is enabled."),
            )

        return cleaned_data
