"""The event log used to grow without bound.

The SSE endpoint polls it twice a second for as long as a dashboard tab is
open, and each poll copied the whole list, so a long session grew the log
without limit and made every poll more expensive.
"""

import logging

from astra.runtime.event_bus import EventBus, RuntimeEvent


def _event(name: str = "index.started") -> RuntimeEvent:
    return RuntimeEvent(event_type=name, payload={}, source="test")


def test_the_log_is_bounded():
    logging.disable(logging.CRITICAL)
    bus = EventBus(max_log=50)
    for i in range(500):
        bus.emit(_event(f"e{i}"))
    assert len(bus.log()) == 50
    # The newest survive, the oldest are dropped.
    assert bus.log()[-1].event_type == "e499"
    assert bus.log()[0].event_type == "e450"


def test_log_since_returns_only_new_events():
    logging.disable(logging.CRITICAL)
    bus = EventBus()
    bus.emit(_event("first"))
    cursor = len(bus.log())

    bus.emit(_event("second"))
    bus.emit(_event("third"))

    new_events, new_cursor = bus.log_since(cursor)
    assert [e.event_type for e in new_events] == ["second", "third"]
    assert new_cursor == 3

    # Polling again with the new cursor yields nothing, not a repeat.
    again, _ = bus.log_since(new_cursor)
    assert again == []


def test_a_cursor_left_past_the_trim_point_does_not_hide_events():
    """After a flush or a trim the old index is out of range. Returning the
    whole log is correct; returning nothing would silently stall the stream."""
    logging.disable(logging.CRITICAL)
    bus = EventBus(max_log=10)
    for i in range(50):
        bus.emit(_event(f"e{i}"))

    new_events, cursor = bus.log_since(999)
    assert len(new_events) == 10
    assert cursor == 10

    # A cursor inside the retained window slices from the current positions.
    # Indices are not stable across a trim — the deque dropped the front, so
    # slot 5 now holds e45, not e5 — which is exactly why an out-of-range
    # cursor has to fall back to the whole window rather than guess.
    windowed, _ = bus.log_since(5)
    assert [e.event_type for e in windowed] == [f"e{i}" for i in range(45, 50)]


def test_flush_empties_the_log():
    logging.disable(logging.CRITICAL)
    bus = EventBus()
    bus.emit(_event())
    bus.flush()
    assert bus.log() == []
    assert bus.log_since(0) == ([], 0)


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
