"""Signal-dispatch behaviour: handlers must not block the request cycle
and must defer API work until the DB transaction commits.
"""

from unittest.mock import patch

from ..signals import _schedule


def test_schedule_without_transaction_runs_immediately():
    calls = []
    _schedule(lambda *a: calls.append(a), 1, 2)
    assert calls == [(1, 2)]


def test_schedule_never_raises_even_if_func_raises():
    def boom(*a):
        raise RuntimeError("should not escape")

    # Must not propagate — signals should never break the order flow
    _schedule(boom, 1)


@patch("pretix_ticketswap.signals._schedule")
def test_order_placed_handler_dispatches_when_enabled(mock_schedule):
    """Verify the handler schedules work rather than running it inline."""
    from ..signals import handle_order_placed

    class FakeSettings:
        def __init__(self, enabled):
            self._enabled = enabled

        def get(self, key, as_type=bool, default=False):
            return True if key == "ticketswap_enabled" and self._enabled else default

    class FakeEvent:
        slug = "e"
        settings = FakeSettings(enabled=True)
        pk = 1

    class FakeOrder:
        code = "ORD1"
        pk = 42

    handle_order_placed(sender=FakeEvent(), order=FakeOrder())
    assert mock_schedule.called


@patch("pretix_ticketswap.signals._schedule")
def test_order_placed_skipped_when_disabled(mock_schedule):
    from ..signals import handle_order_placed

    class FakeSettings:
        def get(self, key, as_type=bool, default=False):
            return False

    class FakeEvent:
        slug = "e"
        settings = FakeSettings()
        pk = 1

    class FakeOrder:
        code = "ORD1"
        pk = 42

    handle_order_placed(sender=FakeEvent(), order=FakeOrder())
    assert not mock_schedule.called
