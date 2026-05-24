"""
GDPR-compliant data shredder for SecureSwap.

Strips ``meta_info.ticketswap`` from orders and positions, including the
customer dict captured during /swap and /personalize. Event-level
settings (token, venue config) are preserved because they're not
personal data.
"""

import json

from django.utils.translation import gettext_lazy as _
from pretix.base.shredder import BaseDataShredder

from .utils import dump_meta, ensure_dict


class TicketSwapDataShredder(BaseDataShredder):
    verbose_name = _("SecureSwap (TicketSwap) Data")
    identifier = "ticketswap_data"
    description = _(
        "Removes all SecureSwap-related data from orders and positions, "
        "including buyer details captured during a resale (name, email, "
        "phone, birthdate) and lock/swap state."
    )

    def generate_files(self):
        """Emit a JSON export of the data we are about to delete."""
        orders = list(
            self.event.orders.filter(
                meta_info__contains='"ticketswap"'
            ).prefetch_related("positions")
        )

        records = []
        for order in orders:
            order_meta = ensure_dict(order.meta_info).get("ticketswap")
            if order_meta:
                records.append({
                    "order_code": order.code,
                    "scope": "order",
                    "ticketswap": order_meta,
                })
            for position in order.positions.all():
                pos_meta = ensure_dict(position.meta_info).get("ticketswap")
                if pos_meta:
                    records.append({
                        "order_code": order.code,
                        "scope": "position",
                        "position_id": position.id,
                        "ticketswap": pos_meta,
                    })

        if records:
            yield (
                "ticketswap_data.json",
                "application/json",
                json.dumps(records, indent=2, default=str),
            )

    def shred_data(self):
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
                order.meta_info = dump_meta(meta)
                orders_to_update.append(order)
            for position in order.positions.all():
                pos_meta = ensure_dict(position.meta_info)
                if "ticketswap" in pos_meta:
                    del pos_meta["ticketswap"]
                    position.meta_info = dump_meta(pos_meta)
                    positions_to_update.append(position)

        if orders_to_update:
            type(orders_to_update[0]).objects.bulk_update(
                orders_to_update, ["meta_info"], batch_size=500
            )
        if positions_to_update:
            type(positions_to_update[0]).objects.bulk_update(
                positions_to_update, ["meta_info"], batch_size=500
            )

        return _("SecureSwap data has been removed.")
