"""
Shared utilities for the TicketSwap plugin.
"""

import json


def ensure_dict(meta_info):
    """Normalise Pretix's ``meta_info`` field to a Python dict.

    Pretix stores ``meta_info`` as a JSON-encoded string in a TextField,
    but different code paths may hand us a str, a dict, or ``None``.
    """
    if isinstance(meta_info, str):
        if not meta_info:
            return {}
        try:
            return json.loads(meta_info)
        except (ValueError, TypeError):
            return {}
    if meta_info is None:
        return {}
    if isinstance(meta_info, dict):
        return meta_info
    return {}


def dump_meta(meta):
    """Serialise a meta dict back to the JSON string Pretix expects."""
    return json.dumps(meta or {}, ensure_ascii=False)
