"""
Shared utilities for the TicketSwap plugin.
"""

import json


def ensure_dict(meta_info):
    """Safely convert meta_info to a dict regardless of storage format.

    Pretix stores meta_info as either a dict or a JSON string depending
    on the context.  This helper normalises both forms.
    """
    if isinstance(meta_info, str):
        return json.loads(meta_info) if meta_info else {}
    if meta_info is None:
        return {}
    return meta_info
