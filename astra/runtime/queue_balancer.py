from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class WorkerStatus:
    worker_id: str
    queue_depth: int
    avg_latency_ms: float
    last_heartbeat: float
    active: bool = True


class QueueBalancer:
    """Distributes tasks across workers using least-loaded strategy."""

    def __init__(self, rebalance_interval: float = 10.0) -> None:
        self._workers: dict[str, WorkerStatus] = {}
        self._rebalance_interval = rebalance_interval
        self._last_rebalance = 0.0

    def register_worker(self, worker_id: str) -> None:
        self._workers[worker_id] = WorkerStatus(
            worker_id=worker_id,
            queue_depth=0,
            avg_latency_ms=0.0,
            last_heartbeat=time.time()
        )

    def unregister_worker(self, worker_id: str) -> None:
        self._workers.pop(worker_id, None)

    def heartbeat(self, worker_id: str, queue_depth: int, avg_latency_ms: float) -> None:
        if worker_id in self._workers:
            self._workers[worker_id].queue_depth = queue_depth
            self._workers[worker_id].avg_latency_ms = avg_latency_ms
            self._workers[worker_id].last_heartbeat = time.time()

    def select_worker(self) -> str | None:
        """Select the least loaded worker."""
        active = [w for w in self._workers.values() if w.active]
        if not active:
            return None
        # Score: lower is better (depth weighted + latency)
        best = min(active, key=lambda w: w.queue_depth * 10 + w.avg_latency_ms)
        self._workers[best.worker_id].queue_depth += 1
        return best.worker_id

    def task_completed(self, worker_id: str, latency_ms: float) -> None:
        if worker_id in self._workers:
            self._workers[worker_id].queue_depth = max(0, self._workers[worker_id].queue_depth - 1)
            # Exponential moving average
            self._workers[worker_id].avg_latency_ms = (
                0.8 * self._workers[worker_id].avg_latency_ms + 0.2 * latency_ms
            )

    def should_rebalance(self) -> bool:
        return time.time() - self._last_rebalance > self._rebalance_interval

    def rebalance(self) -> None:
        self._last_rebalance = time.time()
        # Could migrate tasks from overloaded to underloaded workers
        pass

    def get_stats(self) -> dict[str, Any]:
        return {
            w.worker_id: {
                "queue_depth": w.queue_depth,
                "avg_latency_ms": w.avg_latency_ms,
                "active": w.active
            }
            for w in self._workers.values()
        }
