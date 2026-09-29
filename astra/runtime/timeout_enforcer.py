from __future__ import annotations

import time
import threading
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from typing import Optional


class TimeoutExceeded(Exception):
    """Raised when execution exceeds its deadline."""
    pass


@dataclass
class Deadline:
    """A task execution deadline."""
    task_id: str
    deadline_seconds: float
    escalation_callback: Optional[object] = None
    _start: float = 0.0

    def is_exceeded(self) -> bool:
        return time.time() - self._start > self.deadline_seconds

    def remaining(self) -> float:
        elapsed = time.time() - self._start
        return max(0.0, self.deadline_seconds - elapsed)


class TimeoutEnforcer:
    """Per-task timeout enforcement with escalation."""

    def __init__(self) -> None:
        self._deadlines: dict[str, Deadline] = {}
        self._timers: dict[str, threading.Timer] = {}
        self._escalation_callbacks: dict[str, object] = {}

    def set_deadline(
        self,
        task_id: str,
        timeout_seconds: float,
        escalation_callback=None,
    ) -> Deadline:
        """Set execution deadline for a task."""
        deadline = Deadline(
            task_id=task_id,
            deadline_seconds=timeout_seconds,
            escalation_callback=escalation_callback,
            _start=time.time(),
        )
        self._deadlines[task_id] = deadline

        # Setup auto-cancel timer
        timer = threading.Timer(
            timeout_seconds,
            self._trigger_timeout,
            args=[task_id],
        )
        self._timers[task_id] = timer
        if escalation_callback:
            self._escalation_callbacks[task_id] = escalation_callback
        timer.start()
        return deadline

    def _trigger_timeout(self, task_id: str) -> None:
        """Called when timeout fires."""
        if task_id in self._escalation_callbacks:
            cb = self._escalation_callbacks[task_id]
            if callable(cb):
                with suppress(Exception):
                    cb(task_id)

    def check(self, task_id: str) -> bool:
        """Returns True if deadline exceeded."""
        deadline = self._deadlines.get(task_id)
        if deadline is None:
            return False
        return deadline.is_exceeded()

    def remaining(self, task_id: str) -> float:
        """Get remaining seconds for a task."""
        deadline = self._deadlines.get(task_id)
        if deadline is None:
            return float("inf")
        return deadline.remaining()

    def clear(self, task_id: str) -> None:
        """Clear deadline for a completed task."""
        timer = self._timers.pop(task_id, None)
        if timer:
            timer.cancel()
        self._deadlines.pop(task_id, None)
        self._escalation_callbacks.pop(task_id, None)

    @contextmanager
    def enforce(self, task_id: str, timeout_seconds: float, escalation_callback=None):
        """Context manager that enforces timeout."""
        deadline = self.set_deadline(task_id, timeout_seconds, escalation_callback)
        try:
            yield deadline
        finally:
            self.clear(task_id)
