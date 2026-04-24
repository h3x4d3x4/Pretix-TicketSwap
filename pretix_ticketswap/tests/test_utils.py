"""Tests for utils.ensure_dict / utils.dump_meta round-tripping."""

import json

from ..utils import dump_meta, ensure_dict


def test_ensure_dict_none():
    assert ensure_dict(None) == {}


def test_ensure_dict_empty_string():
    assert ensure_dict("") == {}


def test_ensure_dict_passes_dict_through():
    d = {"ticketswap": {"listed": True}}
    assert ensure_dict(d) is d


def test_ensure_dict_parses_valid_json_string():
    assert ensure_dict('{"a": 1}') == {"a": 1}


def test_ensure_dict_swallows_malformed_json():
    # Historically meta_info could be corrupted by assigning a dict to a
    # TextField (Python repr gets stored). We treat that as empty rather
    # than crashing the signal pipeline.
    assert ensure_dict("{'a': 1}") == {}


def test_ensure_dict_rejects_non_str_non_dict_non_none():
    assert ensure_dict(123) == {}


def test_dump_meta_produces_valid_json():
    out = dump_meta({"ticketswap": {"listed": True}})
    assert isinstance(out, str)
    assert json.loads(out) == {"ticketswap": {"listed": True}}


def test_dump_meta_round_trip_through_ensure_dict():
    meta = {"ticketswap": {"ticket_id": "abc", "listed": True}}
    assert ensure_dict(dump_meta(meta)) == meta


def test_dump_meta_handles_none():
    assert dump_meta(None) == "{}"


def test_dump_meta_preserves_unicode():
    meta = {"attendee": "Renée"}
    assert ensure_dict(dump_meta(meta)) == meta
