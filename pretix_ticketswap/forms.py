"""
Django forms for TicketSwap plugin configuration.
"""

from django import forms
from django.utils.translation import gettext_lazy as _


class TicketSwapSettingsForm(forms.Form):
    """Form for configuring TicketSwap integration settings."""

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
        help_text=_("Your TicketSwap API secret. Keep this confidential."),
        required=False,
        widget=forms.PasswordInput(attrs={"placeholder": "••••••••"}),
    )

    ticketswap_webhook_secret = forms.CharField(
        label=_("Webhook Secret"),
        help_text=_(
            "Secret used to verify incoming webhooks from TicketSwap. "
            "Obtain this from your TicketSwap partnership dashboard."
        ),
        required=False,
        widget=forms.PasswordInput(attrs={"placeholder": "••••••••"}),
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

    def clean(self):
        """Validate form data."""
        cleaned_data = super().clean()
        enabled = cleaned_data.get("ticketswap_enabled")
        api_key = cleaned_data.get("ticketswap_api_key")
        api_secret = cleaned_data.get("ticketswap_api_secret")

        if enabled:
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
            # NOTE: Connection validation removed from form clean().
            # Use the "Test Connection" button instead. This prevents
            # form saves from hanging when the TicketSwap API is unreachable.

        return cleaned_data
