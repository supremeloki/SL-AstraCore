from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Any
from collections import defaultdict
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

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[RuntimeEvent], None]]] = defaultdict(list)
        self._event_log: list[RuntimeEvent] = []

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

    def flush(self) -> None:
        self._event_log.clear()
