from __future__ import annotations

import heapq
import time
from dataclasses import dataclass, field
from enum import IntEnum, auto
from typing import Any, Optional


class Priority(IntEnum):
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


@dataclass(order=True)
class ScheduledTask:
    priority: Priority
    scheduled_at: float
    task_id: str = field(compare=False)
    action: str = field(compare=False)
    payload: dict[str, Any] = field(default_factory=dict, compare=False)
    tags: dict[str, str] = field(default_factory=dict, compare=False)


class AdaptiveScheduler:
    """Priority-aware task scheduler with backpressure-based throttling."""

    def __init__(self, max_queue_depth: int = 1000) -> None:
        self._queue: list[ScheduledTask] = []
        self._max_depth = max_queue_depth
        self._completed: list[str] = []
        self._failed: list[tuple[str, str]] = []  # (task_id, error)

    def enqueue(
        self,
        task_id: str,
        action: str,
        priority: Priority = Priority.NORMAL,
        delay: float = 0.0,
        payload: dict[str, Any] | None = None,
        tags: dict[str, str] | None = None,
    ) -> str:
        if len(self._queue) >= self._max_depth:
            raise RuntimeError(f"Queue full ({self._max_depth}), task {task_id} rejected")
        task = ScheduledTask(
            priority=priority,
            scheduled_at=time.time() + delay,
            task_id=task_id,
            action=action,
            payload=payload or {},
            tags=tags or {},
        )
        heapq.heappush(self._queue, task)
        return task_id

    def dequeue(self, now: float | None = None) -> Optional[ScheduledTask]:
        now = now or time.time()
        while self._queue:
            if self._queue[0].scheduled_at > now:
                return None
            task = heapq.heappop(self._queue)
            return task
        return None

    def peek(self, now: float | None = None) -> Optional[ScheduledTask]:
        now = now or time.time()
        while self._queue and self._queue[0].scheduled_at <= now:
            return self._queue[0]
        return None

    def queue_depth(self) -> int:
        return len(self._queue)

    def backpressure(self) -> float:
        """Return 0.0 (no pressure) to 1.0 (full backpressure)."""
        return min(1.0, len(self._queue) / max(self._max_depth, 1))

    def remove(self, task_id: str) -> bool:
        """Remove a pending task by ID."""
        for i, task in enumerate(self._queue):
            if task.task_id == task_id:
                self._queue.pop(i)
                heapq.heapify(self._queue)
                return True
        return False

    def clear(self) -> None:
        self._queue.clear()

    def mark_completed(self, task_id: str) -> None:
        self._completed.append(task_id)

    def mark_failed(self, task_id: str, error: str) -> None:
        self._failed.append((task_id, error))

    def completed_count(self) -> int:
        return len(self._completed)

    def failed_count(self) -> int:
        return len(self._failed)