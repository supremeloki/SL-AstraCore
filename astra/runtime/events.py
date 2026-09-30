"""Streaming execution events for runtime observability."""
from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class ExecutionEventType(Enum):
    PLAN_CREATED = "plan_created"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    RETRY_ATTEMPT = "retry_attempt"
    DRY_RUN_COMPLETE = "dry_run_complete"
    EXECUTION_COMPLETE = "execution_complete"
    EXECUTION_FAILED = "execution_failed"
    ROLLBACK_STARTED = "rollback_started"
    ROLLBACK_COMPLETE = "rollback_complete"
    POLICY_BLOCKED = "policy_blocked"
    AUDIT_RECORD = "audit_record"


@dataclass(frozen=True)
class ExecutionEvent:
    event_type: ExecutionEventType
    payload: dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    source: str = ""
    step_id: str = ""


class EventStream:
    """In-process event bus for execution events.

    Subscribers receive events in order. Thread-safe for append.
    """

    def __init__(self) -> None:
        self._subscribers: list[Callable[[ExecutionEvent], None]] = []
        self._history: list[ExecutionEvent] = []

    def subscribe(self, callback: Callable[[ExecutionEvent], None]) -> None:
        self._subscribers.append(callback)

    def emit(self, event: ExecutionEvent) -> None:
        self._history.append(event)
        for cb in self._subscribers:
            with contextlib.suppress(Exception):
                cb(event)  # subscriber errors must not break the pipeline

    def history(self, event_type: Optional[ExecutionEventType] = None) -> list[ExecutionEvent]:
        if event_type:
            return [e for e in self._history if e.event_type == event_type]
        return list(self._history)

    def clear(self) -> None:
        self._history.clear()
