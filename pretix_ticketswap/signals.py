"""
Django signal handlers for Pretix-TicketSwap integration.

Signal handlers are lightweight dispatchers that offload actual API work
to tasks (tasks.py) to avoid blocking the Django request/response cycle.
"""

import logging

from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from pretix.base.signals import (
    order_canceled,
    order_paid,
    order_placed,
    register_data_shredders,
)
from pretix.control.signals import nav_event_settings

logger = logging.getLogger(__name__)


@receiver(order_placed, dispatch_uid="ticketswap_order_placed")
def handle_order_placed(sender, **kwargs):
    """
    Handle order placement - dispatch async sync to TicketSwap.

    Args:
        sender: Event object
        **kwargs: Contains 'order' object
    """
    order = kwargs.get("order")
    event = sender

    if not event.settings.get("ticketswap_enabled", as_type=bool, default=False):
        return

    logger.info("Order placed for event %s: %s — dispatching TicketSwap sync", event.slug, order.code)

    from .tasks import sync_order_to_ticketswap
    sync_order_to_ticketswap(event.pk, order.pk)


@receiver(order_paid, dispatch_uid="ticketswap_order_paid")
def handle_order_paid(sender, **kwargs):
    """
    Handle order payment - dispatch async ticket listing on TicketSwap.

    Args:
        sender: Event object
        **kwargs: Contains 'order' object
    """
    order = kwargs.get("order")
    event = sender

    if not event.settings.get("ticketswap_enabled", as_type=bool, default=False):
        return

    if not event.settings.get("ticketswap_auto_enable_resale", as_type=bool, default=True):
        return

    logger.info("Order paid for event %s: %s — dispatching ticket listing", event.slug, order.code)

    from .tasks import list_tickets_for_order
    list_tickets_for_order(event.pk, order.pk)


@receiver(order_canceled, dispatch_uid="ticketswap_order_canceled")
def handle_order_canceled(sender, **kwargs):
    """
    Handle order cancellation - dispatch async ticket delisting.

    Args:
        sender: Event object
        **kwargs: Contains 'order' object
    """
    order = kwargs.get("order")
    event = sender

    if not event.settings.get("ticketswap_enabled", as_type=bool, default=False):
        return

    logger.info("Order canceled for event %s: %s — dispatching ticket delisting", event.slug, order.code)

    from .tasks import delist_tickets_for_order
    delist_tickets_for_order(event.pk, order.pk)


@receiver(nav_event_settings, dispatch_uid="ticketswap_nav_settings")
def add_settings_nav(sender, request, **kwargs):
    """
    Add TicketSwap settings to event navigation.

    Args:
        sender: Event object
        request: HTTP request
        **kwargs: Additional arguments

    Returns:
        Navigation item dictionary
    """
    return [
        {
            "label": _("TicketSwap"),
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
            ),
        }
    ]


@receiver(register_data_shredders, dispatch_uid="ticketswap_register_shredder")
def register_shredder(sender, **kwargs):
    """
    Register the TicketSwap data shredder for GDPR compliance.

    Args:
        sender: Event object
        **kwargs: Additional arguments

    Returns:
        Data shredder class
    """
    from .data_shredder import TicketSwapDataShredder

    return TicketSwapDataShredder
