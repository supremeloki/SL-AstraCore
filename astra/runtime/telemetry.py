"""3D — Telemetry & Observability Engine.

Composes all telemetry components for a unified observability surface.
Export formats: structured JSON, Prometheus-compatible text.
"""

from __future__ import annotations

import time
from typing import Any

from astra.runtime.metrics import MetricsCollector
from astra.runtime.event_bus import EventBus, RuntimeEvent
from astra.runtime.tracing import Tracer
from astra.runtime.health import HealthDiagnostics
from astra.runtime.profiling import get_profiler


class TelemetryEngine:
    """Unified telemetry surface for SL-AstraCore runtime."""

    def __init__(self, service_name: str = "astra-runtime") -> None:
        self.metrics = MetricsCollector()
        self.events = EventBus()
        self.tracer = Tracer(service_name)
        self.health = HealthDiagnostics()
        self.profiler = get_profiler()

    def export_json(self) -> dict[str, Any]:
        """Export all telemetry as structured JSON."""
        return {
            "timestamp": time.time(),
            "health": self.health.export_health(),
            "metrics": {
                "counters": dict(self.metrics._counters),
                "gauges": dict(self.metrics._gauges),
                "errors": dict(self.metrics._errors),
            },
            "traces": self.tracer.export_spans(),
            "events": [
                {"type": e.event_type, "source": e.source, "span_id": e.span_id}
                for e in self.events.log()
            ],
        }

    def export_prometheus(self) -> str:
        """Export metrics in Prometheus exposition format."""
        lines: list[str] = []
        for counter_name, counter_value in self.metrics._counters.items():
            lines.append(f'astra_counter_{counter_name} {counter_value}')
        for gauge_name, gauge_value in self.metrics._gauges.items():
            lines.append(f'astra_gauge_{gauge_name} {gauge_value}')
        for error_name, error_count in self.metrics._errors.items():
            lines.append(f'astra_error_{error_name} {error_count}')
        return "\n".join(lines)

    def emit_event(self, event_type: str, payload: Any, source: str = "") -> None:
        """Emit event via event bus."""
        span = self.tracer.get_current_span()
        event = RuntimeEvent(
            event_type=event_type,
            payload=payload,
            source=source,
            span_id=span.span_id if span else "",
        )
        self.events.emit(event)
        self.metrics.increment(f"events.{event_type}")

    def check_health(self) -> dict[str, Any]:
        """Run health checks and return status."""
        return self.health.export_health()
