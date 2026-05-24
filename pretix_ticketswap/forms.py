"""
Settings forms for the SecureSwap plugin.

Two scopes:
- Organizer-level: the partner bearer token TicketSwap will send. Shared
  across all events in the organizer because TicketSwap configures one
  integration per partner.
- Event-level: per-event toggle + presentation overrides (venue, event
  type) + personalization config + barcode display type.
"""

import json
import secrets

from django import forms
from django.utils.translation import gettext_lazy as _

from .auth import EVENT_ENABLED_SETTING, PARTNER_TOKEN_SETTING
from .personalization import (
    DEFAULT_FIELDS,
    PERSONALIZATION_FIELDS_SETTING,
    validate_fields_config,
)


class TicketSwapOrganizerForm(forms.Form):
    """Organizer-scoped settings: the single partner token TicketSwap uses
    to authenticate inbound requests, plus a generator UX.
    """

    ticketswap_partner_token = forms.CharField(
        label=_("Partner Bearer Token"),
        help_text=_(
            "Token TicketSwap will send in the Authorization header. "
            "Share this with TicketSwap once and keep it secret. "
            "Leave blank to keep the currently stored value."
        ),
        required=False,
        widget=forms.PasswordInput(attrs={"placeholder": "••••••••"}, render_value=False),
    )
    rotate_token = forms.BooleanField(
        label=_("Generate a new token"),
        help_text=_(
            "Replaces the stored token with a freshly-generated one. "
            "You'll need to re-share it with TicketSwap after saving."
        ),
        required=False,
    )

    def __init__(self, *args, organizer=None, **kwargs):
        self.organizer = organizer
        super().__init__(*args, **kwargs)

    @classmethod
    def initial_from_organizer(cls, organizer):
        # Token field intentionally left blank — we don't echo secrets back.
        return {}

    def save_to_organizer(self, organizer):
        if self.cleaned_data.get("rotate_token"):
            new_token = secrets.token_urlsafe(40)
            organizer.settings.set(PARTNER_TOKEN_SETTING, new_token)
            return
        token = self.cleaned_data.get("ticketswap_partner_token") or ""
        if token:
            organizer.settings.set(PARTNER_TOKEN_SETTING, token)


class TicketSwapEventForm(forms.Form):
    """Per-event settings."""

    ticketswap_enabled = forms.BooleanField(
        label=_("Enable SecureSwap for this event"),
        help_text=_(
            "When enabled, TicketSwap can validate and reissue barcodes for "
            "this event's tickets. The organizer-level partner token must "
            "also be configured."
        ),
        required=False,
    )

    ticketswap_personalization_required = forms.BooleanField(
        label=_("Require personalization"),
        help_text=_(
            "If on, /swap returns pdf:null and TicketSwap is expected to "
            "call /personalize before delivering the PDF."
        ),
        required=False,
    )

    ticketswap_event_type = forms.ChoiceField(
        label=_("Event type"),
        choices=[
            ("OTHER", "Other"),
            ("FESTIVAL", "Festival"),
            ("CONCERT", "Concert"),
            ("CLUB", "Club"),
            ("THEATRE", "Theatre"),
            ("SPORT", "Sport"),
            ("CONFERENCE", "Conference"),
            ("EXHIBITION", "Exhibition"),
            ("COMEDY", "Comedy"),
            ("WORKSHOP", "Workshop"),
            ("TALK", "Talk"),
            ("SCREENING", "Screening"),
            ("PARTY", "Party"),
            ("MUSEUM", "Museum"),
            ("AMUSEMENT-PARK", "Amusement Park"),
        ],
        required=False,
        initial="OTHER",
    )

    ticketswap_venue_name = forms.CharField(
        label=_("Venue name"),
        help_text=_("Defaults to the event's location field."),
        required=False,
    )
    ticketswap_venue_city = forms.CharField(
        label=_("Venue city"),
        required=False,
    )
    ticketswap_venue_country = forms.CharField(
        label=_("Venue country (ISO 3166-1 alpha-2)"),
        max_length=2,
        required=False,
    )

    ticketswap_barcode_type = forms.ChoiceField(
        label=_("Barcode rendering type"),
        choices=[
            ("QR-Code", "QR-Code"),
            ("CODE-128", "CODE-128"),
            ("CODE-39", "CODE-39"),
            ("CODE-93", "CODE-93"),
            ("EAN-13", "EAN-13"),
            ("EAN-8", "EAN-8"),
            ("DATAMATRIX", "Datamatrix"),
            ("AZTEC", "Aztec"),
            ("PDF417", "PDF417"),
        ],
        required=False,
        initial="QR-Code",
    )

    ticketswap_swap_available_until = forms.CharField(
        label=_("Swap available until (ISO 8601)"),
        help_text=_(
            "Optional cut-off timestamp after which barcodes can no longer "
            "be reissued. Example: 2026-07-12T10:00:00+02:00"
        ),
        required=False,
    )

    ticketswap_sealed_available_at = forms.CharField(
        label=_("Sealed tickets available at (ISO 8601)"),
        help_text=_(
            "If set, declares this event as sealed and tells TicketSwap "
            "when tickets become available to buyers."
        ),
        required=False,
    )

    ticketswap_personalization_fields = forms.CharField(
        label=_("Personalization fields (JSON)"),
        help_text=_(
            "JSON array of personalization-field definitions matching the "
            "/personalization-fields response shape. Leave blank to use a "
            "minimal first_name + last_name default."
        ),
        required=False,
        widget=forms.Textarea(attrs={"rows": 10, "class": "font-monospace"}),
    )

    ticketswap_excluded_item_ids = forms.CharField(
        label=_("Excluded item IDs"),
        help_text=_(
            "Comma-separated Pretix item IDs that may not be resold "
            "(e.g., guest list passes)."
        ),
        required=False,
    )

    def __init__(self, *args, event=None, **kwargs):
        self.event = event
        super().__init__(*args, **kwargs)

    @classmethod
    def initial_from_event(cls, event):
        keys = (
            EVENT_ENABLED_SETTING,
            "ticketswap_personalization_required",
            "ticketswap_event_type",
            "ticketswap_venue_name",
            "ticketswap_venue_city",
            "ticketswap_venue_country",
            "ticketswap_barcode_type",
            "ticketswap_swap_available_until",
            "ticketswap_sealed_available_at",
            PERSONALIZATION_FIELDS_SETTING,
            "ticketswap_excluded_item_ids",
        )
        initial = {}
        for k in keys:
            v = event.settings.get(k, as_type=str, default="")
            if v:
                if k in (EVENT_ENABLED_SETTING, "ticketswap_personalization_required"):
                    initial[k] = v in ("True", "true", "1")
                else:
                    initial[k] = v
        if not initial.get(PERSONALIZATION_FIELDS_SETTING):
            initial[PERSONALIZATION_FIELDS_SETTING] = json.dumps(DEFAULT_FIELDS, indent=2)
        return initial

    def clean_ticketswap_personalization_fields(self):
        raw = (self.cleaned_data.get("ticketswap_personalization_fields") or "").strip()
        if not raw:
            return ""
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            raise forms.ValidationError(_("Not valid JSON."))
        errors = validate_fields_config(parsed)
        if errors:
            raise forms.ValidationError("; ".join(errors))
        return raw

    def clean_ticketswap_venue_country(self):
        v = (self.cleaned_data.get("ticketswap_venue_country") or "").strip().upper()
        if v and len(v) != 2:
            raise forms.ValidationError(
                _("Country must be a 2-letter ISO 3166-1 alpha-2 code.")
            )
        return v

    def save_to_event(self, event):
        # Booleans serialize correctly through Hierarkey; strings as-is.
        for key in (
            EVENT_ENABLED_SETTING,
            "ticketswap_personalization_required",
        ):
            event.settings.set(key, bool(self.cleaned_data.get(key)))
        for key in (
            "ticketswap_event_type",
            "ticketswap_venue_name",
            "ticketswap_venue_city",
            "ticketswap_venue_country",
            "ticketswap_barcode_type",
            "ticketswap_swap_available_until",
            "ticketswap_sealed_available_at",
            PERSONALIZATION_FIELDS_SETTING,
            "ticketswap_excluded_item_ids",
        ):
            event.settings.set(key, self.cleaned_data.get(key) or "")
