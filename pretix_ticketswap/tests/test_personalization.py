"""Personalization-field schema + validation tests."""

import json
from types import SimpleNamespace

from ..personalization import (
    DEFAULT_FIELDS,
    PERSONALIZATION_FIELDS_SETTING,
    get_fields_for_event,
    validate_fields_config,
)


def _event_with_setting(value):
    class FakeSettings:
        def get(self, key, as_type=str, default=""):
            return value if key == PERSONALIZATION_FIELDS_SETTING else default
    return SimpleNamespace(slug="e", settings=FakeSettings())


def test_default_fields_returned_when_unset():
    fields = get_fields_for_event(_event_with_setting(""))
    assert fields == DEFAULT_FIELDS
    # Don't return the module-level list directly — caller might mutate it.
    assert fields is not DEFAULT_FIELDS


def test_default_fields_returned_on_corrupt_json():
    fields = get_fields_for_event(_event_with_setting("not valid json {"))
    assert fields == DEFAULT_FIELDS


def test_configured_fields_returned_when_valid():
    cfg = [
        {"name": "first_name", "label": "First", "type": "text",
         "is_required": True, "sort_order": 0},
    ]
    fields = get_fields_for_event(_event_with_setting(json.dumps(cfg)))
    assert fields == cfg


def test_validate_accepts_minimal_valid_config():
    cfg = [
        {"name": "first_name", "label": "First", "type": "text",
         "is_required": True, "sort_order": 0},
        {"name": "last_name", "label": "Last", "type": "text",
         "is_required": True, "sort_order": 1},
    ]
    assert validate_fields_config(cfg) == []


def test_validate_rejects_non_list_top_level():
    errors = validate_fields_config({"not": "a list"})
    assert errors and "array" in errors[0]


def test_validate_rejects_unknown_type():
    errors = validate_fields_config([{
        "name": "x", "label": "X", "type": "bogus",
        "is_required": True, "sort_order": 0,
    }])
    assert any("bogus" in e for e in errors)


def test_validate_rejects_missing_required_key():
    errors = validate_fields_config([{"name": "x", "label": "X", "type": "text"}])
    assert any("is_required" in e for e in errors)
    assert any("sort_order" in e for e in errors)


def test_validate_rejects_duplicate_names():
    errors = validate_fields_config([
        {"name": "x", "label": "1", "type": "text", "is_required": True, "sort_order": 0},
        {"name": "x", "label": "2", "type": "text", "is_required": True, "sort_order": 1},
    ])
    assert any("duplicate" in e for e in errors)


def test_validate_choice_requires_choices_list():
    errors = validate_fields_config([{
        "name": "title", "label": "Title", "type": "single_choice",
        "is_required": True, "sort_order": 0,
    }])
    assert any("choices" in e for e in errors)
