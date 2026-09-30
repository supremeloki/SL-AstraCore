from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Any
from collections import defaultdict, deque
import contextlib


@dataclass
class RuntimeEvent:
    event_type: str
    payload: Any
    source: str = ""
    span_id: str = ""
    tags: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class EventBus:
    """Pub/sub event bus for runtime events."""

    def __init__(self, max_log: int = 1000) -> None:
        self._subscribers: dict[str, list[Callable[[RuntimeEvent], None]]] = defaultdict(list)
        # Bounded: the SSE endpoint polls this twice a second for the life of
        # the dashboard, so an unbounded list grew forever and every poll copied
        # it in full.
        self._event_log: deque[RuntimeEvent] = deque(maxlen=max_log)

    def subscribe(self, event_type: str, handler: Callable[[RuntimeEvent], None]) -> None:
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Callable[[RuntimeEvent], None]) -> None:
        self._subscribers[event_type] = [h for h in self._subscribers[event_type] if h is not handler]

    def emit(self, event: RuntimeEvent) -> None:
        self._event_log.append(event)
        for handler in self._subscribers.get(event.event_type, ()):
            with contextlib.suppress(Exception):
                handler(event)

    def log(self) -> list[RuntimeEvent]:
        return list(self._event_log)

    def log_since(self, index: int) -> tuple[list[RuntimeEvent], int]:
        """Events after `index`, plus the new index.

        Callers poll this, so it hands back the new cursor instead of making
        them call len(log()). A cursor at or past the end (the log was trimmed
        or flushed underneath it) returns the whole retained window once, so
        the stream recovers instead of stalling.
        """
        events = list(self._event_log)
        if index >= len(events):
            if index == len(events):
                return [], index
            return events, len(events)
        return events[index:], len(events)

    def flush(self) -> None:
        self._event_log.clear()
