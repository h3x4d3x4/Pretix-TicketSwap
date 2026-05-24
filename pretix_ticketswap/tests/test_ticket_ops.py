"""
Domain-operation tests: eligibility predicates, UUID cache, and the
``_trim_customer`` whitelist behavior.

Heavy DB-touching paths (swap_barcode, lock_position) are covered
indirectly via the view smoke tests in ``test_views.py``; here we
exercise the parts that can be tested without spinning up a pretix DB.
"""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.test import override_settings

from ..serializers import position_uuid
from ..ticket_ops import (
    OrderCancelled,
    ResellNotAllowed,
    TicketAlreadyScanned,
    TicketAlreadySwapped,
    _trim_customer,
    _uuid_cache_key,
    assert_swappable,
    find_position_by_ticket_uuid,
    remember_uuid_for_position,
)

# Pretix test settings use DummyCache; force a real local cache for the
# cache-behavior tests below.
LOCMEM_CACHE = override_settings(CACHES={
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
})


def _settings_with(d):
    class S:
        def get(self, key, as_type=str, default=False):
            return d.get(key, default)
    return S()


def _event(pk=1, slug="e", enabled=True):
    return SimpleNamespace(
        pk=pk, slug=slug, currency="EUR",
        date_from=datetime(2026, 7, 12, tzinfo=timezone.utc),
        date_to=datetime(2026, 7, 13, tzinfo=timezone.utc),
        location="", name="X",
        settings=_settings_with({"ticketswap_enabled": enabled}),
        organizer_id=42,
    )


def _position(secret="ABC", status="p", canceled=False, price="20.00", meta_info="",
              event=None, has_checkins=False):
    e = event or _event()
    item = SimpleNamespace(pk=10, name="GA", default_price=Decimal(price), event=e)
    checkins = SimpleNamespace(exists=lambda: has_checkins)
    return SimpleNamespace(
        pk=99, secret=secret, canceled=canceled, price=Decimal(price),
        meta_info=meta_info, item=item, checkins=checkins,
        order=SimpleNamespace(event=e, status=status, code="ORD1"),
    )


# ---- Eligibility ----------------------------------------------------------


def test_swappable_passes_for_paid_uncanceled_position():
    assert_swappable(_position())  # no exception


def test_swappable_rejects_canceled_position():
    with pytest.raises(OrderCancelled):
        assert_swappable(_position(canceled=True))


def test_swappable_rejects_canceled_order():
    with pytest.raises(OrderCancelled):
        assert_swappable(_position(status="c"))


def test_swappable_rejects_expired_order():
    with pytest.raises(OrderCancelled):
        assert_swappable(_position(status="e"))


def test_swappable_rejects_pending_order():
    with pytest.raises(ResellNotAllowed):
        assert_swappable(_position(status="n"))


def test_swappable_rejects_free_ticket():
    with pytest.raises(ResellNotAllowed):
        assert_swappable(_position(price="0.00"))


def test_swappable_rejects_scanned_via_checkins():
    with pytest.raises(TicketAlreadyScanned):
        assert_swappable(_position(has_checkins=True))


def test_swappable_rejects_when_meta_marks_swapped():
    pos = _position(meta_info='{"ticketswap": {"swapped_to": "OLD"}}')
    with pytest.raises(TicketAlreadySwapped):
        assert_swappable(pos)


def test_swappable_handles_missing_checkins_attribute():
    """Some test doubles / older pretix versions don't expose .checkins."""
    e = _event()
    item = SimpleNamespace(pk=1, name="GA", default_price=Decimal("10.00"), event=e)
    pos = SimpleNamespace(
        pk=1, secret="X", canceled=False, price=Decimal("10.00"),
        meta_info="", item=item,
        order=SimpleNamespace(event=e, status="p", code="ORD1"),
        # no .checkins attribute at all
    )
    assert_swappable(pos)  # must not raise


# ---- Customer trimming ----------------------------------------------------


def test_trim_customer_keeps_only_known_fields():
    out = _trim_customer({
        "firstName": "Alice",
        "lastName": "Doe",
        "email": "a@b.com",
        "language": "en",
        "phone": "+31",
        "password": "haha",  # not a real field — must be dropped
        "is_admin": True,
    })
    assert set(out) == {"firstName", "lastName", "email", "language", "phone"}


def test_trim_customer_handles_empty_input():
    assert _trim_customer({}) == {}


def test_trim_customer_omits_missing_optional_fields():
    out = _trim_customer({"firstName": "A", "lastName": "B",
                          "email": "x@y.com", "language": "nl"})
    assert "phone" not in out
    assert "birthdate" not in out


# ---- UUID cache lookup ----------------------------------------------------


def _organizer():
    return SimpleNamespace(pk=42, slug="org")


@LOCMEM_CACHE
def test_remember_uuid_writes_to_cache():
    organizer = _organizer()
    pos = SimpleNamespace(pk=123)
    cache.delete(_uuid_cache_key(organizer.pk, position_uuid(pos)))
    remember_uuid_for_position(organizer, pos)
    assert cache.get(_uuid_cache_key(organizer.pk, position_uuid(pos))) == 123


@LOCMEM_CACHE
@patch("pretix_ticketswap.ticket_ops.is_event_enabled", return_value=True)
def test_find_position_by_ticket_uuid_uses_cache(_mock_enabled):
    organizer = _organizer()
    pos = SimpleNamespace(pk=555)
    uuid = position_uuid(pos)
    cache.set(_uuid_cache_key(organizer.pk, uuid), 555, 60)

    # The cache hit path calls OrderPosition.objects.get(pk=...).
    from pretix.base.models import OrderPosition
    e = _event()
    real_pos = SimpleNamespace(
        pk=555, secret="X",
        order=SimpleNamespace(event=e),
    )
    fake_qs = MagicMock()
    fake_qs.select_related.return_value = fake_qs
    fake_qs.get.return_value = real_pos
    with patch.object(OrderPosition, "objects", fake_qs):
        result = find_position_by_ticket_uuid(organizer, uuid)

    assert result is real_pos
    # Cache hit means we never hit the scanning queryset
    fake_qs.filter.assert_not_called()


def test_find_position_by_ticket_uuid_returns_none_for_empty_uuid():
    assert find_position_by_ticket_uuid(_organizer(), "") is None
    assert find_position_by_ticket_uuid(_organizer(), None) is None
