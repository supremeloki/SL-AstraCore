from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MetricSnapshot:
    name: str
    value: float
    tags: dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class MetricsCollector:
    """Collects structured runtime metrics: latency, throughput, error rates, counters."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._latencies: dict[str, list[float]] = defaultdict(list)
        self._errors: dict[str, int] = defaultdict(int)
        self._snapshots: list[MetricSnapshot] = []
        self._max_latency_samples = 1000

    def increment(self, name: str, tags: dict[str, str] | None = None) -> None:
        self._counters[name] += 1
        self._snapshots.append(MetricSnapshot(name=f"counter:{name}", value=self._counters[name], tags=tags or {}))

    def gauge(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        self._gauges[name] = value
        self._snapshots.append(MetricSnapshot(name=f"gauge:{name}", value=value, tags=tags or {}))

    def record_latency(self, name: str, seconds: float, tags: dict[str, str] | None = None) -> None:
        samples = self._latencies[name]
        samples.append(seconds)
        if len(samples) > self._max_latency_samples:
            samples.pop(0)
        self._snapshots.append(MetricSnapshot(name=f"latency:{name}", value=seconds, tags=tags or {}))

    def record_error(self, name: str, tags: dict[str, str] | None = None) -> None:
        self._errors[name] += 1
        self._snapshots.append(MetricSnapshot(name=f"error:{name}", value=self._errors[name], tags=tags or {}))

    def latency_p50(self, name: str) -> float:
        samples = sorted(self._latencies[name])
        if not samples:
            return 0.0
        return samples[len(samples) // 2]

    def latency_p99(self, name: str) -> float:
        samples = sorted(self._latencies[name])
        if not samples:
            return 0.0
        return samples[int(len(samples) * 0.99)]

    def throughput(self, name: str, window_seconds: float = 60.0) -> float:
        recent = [s for s in self._snapshots if s.name == f"counter:{name}" and time.time() - s.timestamp < window_seconds]
        return len(recent) / max(window_seconds, 0.001)

    def error_rate(self, name: str) -> float:
        total = self._counters.get(name, 0)
        errors = self._errors.get(name, 0)
        if total == 0:
            return 0.0
        return errors / (total + errors)

    def export_snapshots(self) -> list[MetricSnapshot]:
        return list(self._snapshots)

    def counters(self) -> dict[str, int]:
        return dict(self._counters)

    def reset(self) -> None:
        self._counters.clear()
        self._gauges.clear()
        self._latencies.clear()
        self._errors.clear()
        self._snapshots.clear()