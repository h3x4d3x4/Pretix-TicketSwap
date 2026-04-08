"""
GDPR-compliant data shredder for TicketSwap plugin.

Handles deletion of personal data stored by the plugin.
"""

import json

from django.utils.translation import gettext_lazy as _

from pretix.base.shredder import BaseDataShredder

from .utils import ensure_dict


class TicketSwapDataShredder(BaseDataShredder):
    """
    Data shredder for TicketSwap integration data.

    Removes all TicketSwap-related data from orders and positions
    when a user requests data deletion.
    """

    verbose_name = _("TicketSwap Integration Data")
    identifier = "ticketswap_data"
    description = _(
        "This will remove all data stored by the TicketSwap integration plugin, "
        "including sync status, TicketSwap ticket IDs, and event mappings."
    )

    def generate_files(self):
        """
        Generate downloadable files containing the user's TicketSwap data.

        Yields:
            Tuples of (filename, file_type, file_content)
        """
        orders = self.event.orders.filter(
            meta_info__contains='"ticketswap"'
        ).prefetch_related("positions")

        if orders.exists():
            data = []
            for order in orders:
                meta = ensure_dict(order.meta_info)
                ticketswap_data = meta.get("ticketswap", {})
                if ticketswap_data:
                    data.append({
                        "order_code": order.code,
                        "ticketswap_event_id": ticketswap_data.get("event_id"),
                        "synced": ticketswap_data.get("synced"),
                    })

                for position in order.positions.all():
                    pos_meta = ensure_dict(position.meta_info)
                    pos_ticketswap = pos_meta.get("ticketswap", {})
                    if pos_ticketswap:
                        data.append({
                            "order_code": order.code,
                            "position_id": position.id,
                            "ticketswap_ticket_id": pos_ticketswap.get("ticket_id"),
                            "listed": pos_ticketswap.get("listed"),
                        })

            if data:
                yield (
                    "ticketswap_data.json",
                    "application/json",
                    json.dumps(data, indent=2),
                )

    def shred_data(self):
        """
        Remove all TicketSwap data from the database.

        Uses prefetch_related and bulk_update for efficiency.
        """
        orders = list(
            self.event.orders.filter(
                meta_info__contains='"ticketswap"'
            ).prefetch_related("positions")
        )

        orders_to_update = []
        positions_to_update = []

        for order in orders:
            meta = ensure_dict(order.meta_info)
            if "ticketswap" in meta:
                del meta["ticketswap"]
                order.meta_info = meta
                orders_to_update.append(order)

            for position in order.positions.all():
                pos_meta = ensure_dict(position.meta_info)
                if "ticketswap" in pos_meta:
                    del pos_meta["ticketswap"]
                    position.meta_info = pos_meta
                    positions_to_update.append(position)

        # Bulk update for efficiency
        if orders_to_update:
            type(orders_to_update[0]).objects.bulk_update(
                orders_to_update, ["meta_info"], batch_size=500
            )

        if positions_to_update:
            type(positions_to_update[0]).objects.bulk_update(
                positions_to_update, ["meta_info"], batch_size=500
            )

        return _("TicketSwap integration data has been removed.")
