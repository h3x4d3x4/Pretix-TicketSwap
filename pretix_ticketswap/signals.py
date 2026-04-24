"""
Django signal handlers for Pretix-TicketSwap integration.

Signal handlers are lightweight dispatchers. They schedule the actual
API work to run after the current DB transaction commits (via
``transaction.on_commit``) so a slow or failing TicketSwap call can
never block or roll back a Pretix order.
"""

import logging

from django.db import transaction
from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from pretix.base.signals import order_canceled, order_paid, order_placed, register_data_shredders
from pretix.control.signals import nav_event_settings

logger = logging.getLogger(__name__)


def _enabled(event):
    return event.settings.get("ticketswap_enabled", as_type=bool, default=False)


def _schedule(func, *args):
    """Run ``func(*args)`` once the current DB transaction commits.

    Falls back to immediate execution if ``on_commit`` is not usable
    (no DB connection available, e.g. in tests or management commands).
    Any failure in the scheduled work is caught so it cannot propagate
    into the Pretix order flow.
    """
    try:
        transaction.on_commit(lambda: func(*args))
        return
    except Exception:
        logger.debug("on_commit unavailable, running TicketSwap task inline")
    try:
        func(*args)
    except Exception:
        logger.exception("TicketSwap task failed")


@receiver(order_placed, dispatch_uid="ticketswap_order_placed")
def handle_order_placed(sender, **kwargs):
    order = kwargs.get("order")
    event = sender
    if not order or not _enabled(event):
        return

    logger.info(
        "ticketswap: scheduling order-placed sync event=%s order=%s",
        event.slug, order.code,
    )
    from .tasks import sync_order_to_ticketswap
    _schedule(sync_order_to_ticketswap, event.pk, order.pk)


@receiver(order_paid, dispatch_uid="ticketswap_order_paid")
def handle_order_paid(sender, **kwargs):
    order = kwargs.get("order")
    event = sender
    if not order or not _enabled(event):
        return
    if not event.settings.get("ticketswap_auto_enable_resale", as_type=bool, default=True):
        return

    logger.info(
        "ticketswap: scheduling order-paid listing event=%s order=%s",
        event.slug, order.code,
    )
    from .tasks import list_tickets_for_order
    _schedule(list_tickets_for_order, event.pk, order.pk)


@receiver(order_canceled, dispatch_uid="ticketswap_order_canceled")
def handle_order_canceled(sender, **kwargs):
    order = kwargs.get("order")
    event = sender
    if not order or not _enabled(event):
        return

    logger.info(
        "ticketswap: scheduling order-canceled delisting event=%s order=%s",
        event.slug, order.code,
    )
    from .tasks import delist_tickets_for_order
    _schedule(delist_tickets_for_order, event.pk, order.pk)


@receiver(nav_event_settings, dispatch_uid="ticketswap_nav_settings")
def add_settings_nav(sender, request, **kwargs):
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
    from .data_shredder import TicketSwapDataShredder
    return TicketSwapDataShredder
