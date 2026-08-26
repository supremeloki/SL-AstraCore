"""3D — Telemetry & Observability test suite.

Verifies:
  - MetricsCollector (counters, gauges, latencies, error rates, throughput)
  - EventBus (subscribe, emit, log, unsubscribe)
  - Tracer (start_span, trace context manager, span export)
  - HealthDiagnostics (register check, overall status, system metrics)
  - Profiler (enable/disable, profile context manager)
  - TelemetryEngine (JSON export, Prometheus export, event emission)
"""

from __future__ import annotations

import pytest

from astra.runtime.metrics import MetricsCollector
from astra.runtime.event_bus import EventBus, RuntimeEvent
from astra.runtime.tracing import Tracer
from astra.runtime.health import HealthDiagnostics, HealthStatus, ComponentHealth
from astra.runtime.profiling import Profiler
from astra.runtime.telemetry import TelemetryEngine


class TestMetricsCollector:
    def test_increment_counter(self):
        m = MetricsCollector()
        m.increment("tasks")
        m.increment("tasks")
        assert m._counters["tasks"] == 2

    def test_gauge_set(self):
        m = MetricsCollector()
        m.gauge("queue_depth", 5.0)
        assert m._gauges["queue_depth"] == 5.0

    def test_record_latency(self):
        m = MetricsCollector()
        m.record_latency("index", 0.1)
        m.record_latency("index", 0.2)
        assert len(m._latencies["index"]) == 2
        assert m.latency_p50("index") > 0

    def test_record_error(self):
        m = MetricsCollector()
        m.increment("index")
        m.record_error("index")
        assert m.error_rate("index") == 0.5

    def test_latency_p99(self):
        m = MetricsCollector()
        for i in range(100):
            m.record_latency("test", float(i) / 100.0)
        p99 = m.latency_p99("test")
        assert p99 >= 0.9

    def test_export_snapshots(self):
        m = MetricsCollector()
        m.increment("a")
        m.gauge("b", 1.0)
        assert len(m.export_snapshots()) == 2

    def test_reset(self):
        m = MetricsCollector()
        m.increment("x")
        m.gauge("y", 1.0)
        m.reset()
        assert len(m.export_snapshots()) == 0


class TestEventBus:
    def test_subscribe_and_emit(self):
        bus = EventBus()
        received = []
        bus.subscribe("test", lambda e: received.append(e))
        bus.emit(RuntimeEvent(event_type="test", payload="hello"))
        assert len(received) == 1
        assert received[0].payload == "hello"

    def test_unsubscribe(self):
        bus = EventBus()
        def handler(e):
            return None
        bus.subscribe("test", handler)
        bus.unsubscribe("test", handler)
        bus.emit(RuntimeEvent(event_type="test", payload="x"))
        assert len(bus.log()) == 1

    def test_event_log(self):
        bus = EventBus()
        bus.emit(RuntimeEvent(event_type="a", payload=""))
        bus.emit(RuntimeEvent(event_type="b", payload=""))
        assert len(bus.log()) == 2

    def test_flush(self):
        bus = EventBus()
        bus.emit(RuntimeEvent(event_type="a", payload=""))
        bus.flush()
        assert len(bus.log()) == 0


class TestTracer:
    def test_start_span(self):
        tracer = Tracer()
        span = tracer.start_span("test")
        assert span.name == "test"
        assert span.trace_id is not None
        assert span.span_id is not None

    def test_trace_context_manager(self):
        tracer = Tracer()
        with tracer.trace("op1") as span:
            assert span.name == "op1"
            assert not span.end_time
        assert span.end_time is not None
        assert span.duration_ms >= 0

    def test_nested_spans(self):
        tracer = Tracer()
        with tracer.trace("outer") as outer:
            with tracer.trace("inner", parent=outer) as inner:
                pass
        assert inner.parent_span_id == outer.span_id
        assert len(tracer.export_spans()) == 2

    def test_span_error_handling(self):
        tracer = Tracer()
        with pytest.raises(ValueError):
            with tracer.trace("op"):
                raise ValueError("boom")
        spans = tracer.export_spans()
        assert len(spans) == 1
        assert spans[0]["tags"].get("error") == "true"

    def test_reset(self):
        tracer = Tracer()
        tracer.start_span("x")
        tracer.reset()
        assert len(tracer.export_spans()) == 0


class TestHealthDiagnostics:
    def test_register_and_run(self):
        hd = HealthDiagnostics()
        hd.register_check("db", lambda: ComponentHealth(name="db", status=HealthStatus.HEALTHY))
        checks = hd.run_checks()
        assert checks["db"].status == HealthStatus.HEALTHY

    def test_overall_healthy(self):
        hd = HealthDiagnostics()
        hd.register_check("a", lambda: ComponentHealth(name="a", status=HealthStatus.HEALTHY))
        hd.register_check("b", lambda: ComponentHealth(name="b", status=HealthStatus.HEALTHY))
        assert hd.overall_status() == HealthStatus.HEALTHY

    def test_overall_degraded(self):
        hd = HealthDiagnostics()
        hd.register_check("a", lambda: ComponentHealth(name="a", status=HealthStatus.DEGRADED))
        assert hd.overall_status() == HealthStatus.DEGRADED

    def test_overall_unhealthy(self):
        hd = HealthDiagnostics()
        hd.register_check("a", lambda: ComponentHealth(name="a", status=HealthStatus.UNHEALTHY))
        assert hd.overall_status() == HealthStatus.UNHEALTHY

    def test_system_metrics(self):
        hd = HealthDiagnostics()
        metrics = hd.system_metrics()
        assert "memory_rss_mb" in metrics
        assert "cpu_percent" in metrics

    def test_export_health(self):
        hd = HealthDiagnostics()
        hd.register_check("x", lambda: ComponentHealth(name="x", status=HealthStatus.HEALTHY))
        export = hd.export_health()
        assert export["status"] == "healthy"


class TestProfiler:
    def test_enable_disable(self):
        p = Profiler()
        p.enable()
        assert p._enabled
        result = p.disable()
        assert not p._enabled
        assert result is not None

    def test_profile_context_manager(self):
        p = Profiler()
        with p.profile("test"):
            sum(range(1000))
        assert not p._enabled


class TestTelemetryEngine:
    def test_export_json(self):
        engine = TelemetryEngine()
        engine.metrics.increment("tasks")
        engine.metrics.gauge("queue", 3.0)
        data = engine.export_json()
        assert "timestamp" in data
        assert data["metrics"]["counters"]["tasks"] == 1

    def test_export_prometheus(self):
        engine = TelemetryEngine()
        engine.metrics.increment("index")
        engine.metrics.increment("index")
        prom = engine.export_prometheus()
        assert "astra_counter_index 2" in prom

    def test_emit_event(self):
        engine = TelemetryEngine()
        engine.emit_event("test", {"key": "val"}, source="unit")
        assert len(engine.events.log()) == 1

    def test_check_health(self):
        engine = TelemetryEngine()
        health = engine.check_health()
        assert "status" in health