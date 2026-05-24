"""
Signal hooks for the SecureSwap plugin.

The previous outbound-API plugin used signal handlers to push events
to TicketSwap. That direction is wrong — TicketSwap pulls from us, not
the other way around — so all that machinery is gone.

What remains: nav entries for the admin pages, and the data-shredder
registration for GDPR deletion.
"""

from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from pretix.base.signals import register_data_shredders
from pretix.control.signals import nav_event_settings, nav_organizer


@receiver(nav_event_settings, dispatch_uid="ticketswap_nav_event_settings")
def add_event_nav(sender, request, **kwargs):
    return [
        {
            "label": _("SecureSwap"),
            "url": reverse(
                "plugins:pretix_ticketswap:dashboard",
                kwargs={
                    "event": request.event.slug,
                    "organizer": request.organizer.slug,
                },
            ),
            "active": (
                request.resolver_match is not None
                and request.resolver_match.namespace == "plugins:pretix_ticketswap"
                and "organizer_settings" not in (request.resolver_match.url_name or "")
            ),
        }
    ]


@receiver(nav_organizer, dispatch_uid="ticketswap_nav_organizer")
def add_organizer_nav(sender, request, organizer, **kwargs):
    """Surface the organizer-level partner-token settings page."""
    return [
        {
            "label": _("SecureSwap"),
            "url": reverse(
                "plugins:pretix_ticketswap:organizer_settings",
                kwargs={"organizer": organizer.slug},
            ),
            "active": (
                request.resolver_match is not None
                and (request.resolver_match.url_name or "") == "organizer_settings"
            ),
        }
    ]


@receiver(register_data_shredders, dispatch_uid="ticketswap_register_shredder")
def register_shredder(sender, **kwargs):
    from .data_shredder import TicketSwapDataShredder
    return TicketSwapDataShredder
