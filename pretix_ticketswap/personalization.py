"""
Personalization-fields schema returned by ``/personalization-fields/{barcode}``.

Each event configures its own list of fields (stored as JSON in event
settings). When unconfigured, we fall back to a minimal schema of just
first_name + last_name, which is what most events actually need.
"""

import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

PERSONALIZATION_FIELDS_SETTING = "ticketswap_personalization_fields"

# Spec-defined field types. Validated on save so we never serve a payload
# TicketSwap would reject.
VALID_FIELD_TYPES = {
    "text", "textarea", "number", "single_choice", "multi_choice",
    "date", "time", "datetime", "url", "email", "phone", "birthdate",
    "agreement", "single_checkbox",
}

DEFAULT_FIELDS: List[Dict[str, Any]] = [
    {
        "name": "first_name",
        "label": "First name",
        "type": "text",
        "helper_text": "Enter your first name",
        "is_required": True,
        "sort_order": 0,
    },
    {
        "name": "last_name",
        "label": "Last name",
        "type": "text",
        "helper_text": "Enter your last name",
        "is_required": True,
        "sort_order": 1,
    },
]


def get_fields_for_event(event) -> List[Dict[str, Any]]:
    """Return the per-event configured fields, or the minimal default."""
    raw = event.settings.get(
        PERSONALIZATION_FIELDS_SETTING, as_type=str, default=""
    ) or ""
    if not raw:
        return list(DEFAULT_FIELDS)
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        logger.warning(
            "secureswap: corrupt personalization fields config event=%s — using defaults",
            event.slug,
        )
        return list(DEFAULT_FIELDS)
    return parsed if isinstance(parsed, list) else list(DEFAULT_FIELDS)


def validate_fields_config(parsed) -> List[str]:
    """Return a list of human-readable errors for ``parsed`` (empty if OK).

    Used by the admin form before storing — we'd rather reject a malformed
    config than serve a 500 to TicketSwap later.
    """
    errors = []
    if not isinstance(parsed, list):
        return ["Top level must be a JSON array."]

    seen_names = set()
    for idx, field in enumerate(parsed):
        if not isinstance(field, dict):
            errors.append(f"Entry {idx}: not an object.")
            continue
        for required_key in ("name", "label", "type", "is_required", "sort_order"):
            if required_key not in field:
                errors.append(f"Entry {idx}: missing required key '{required_key}'.")
        if "type" in field and field["type"] not in VALID_FIELD_TYPES:
            errors.append(
                f"Entry {idx}: type '{field['type']}' not in {sorted(VALID_FIELD_TYPES)}."
            )
        if "name" in field:
            if field["name"] in seen_names:
                errors.append(f"Entry {idx}: duplicate name '{field['name']}'.")
            seen_names.add(field["name"])

        # Choice types must include their option list.
        if field.get("type") in ("single_choice", "multi_choice"):
            choices = field.get("choices")
            if not isinstance(choices, list) or not choices:
                errors.append(f"Entry {idx}: '{field.get('type')}' requires a non-empty 'choices' list.")

    return errors
