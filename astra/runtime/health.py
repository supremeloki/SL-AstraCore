from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Any
from enum import Enum
import time
import psutil
import os


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    name: str
    status: HealthStatus
    message: str = ""
    latency_ms: float = 0.0
    last_check: float = field(default_factory=time.time)


class HealthDiagnostics:
    """Health diagnostics with component-level status reporting."""

    def __init__(self) -> None:
        self._checks: dict[str, Callable[[], ComponentHealth]] = {}
        self._process = psutil.Process(os.getpid())

    def register_check(self, name: str, check: Callable[[], ComponentHealth]) -> None:
        self._checks[name] = check

    def run_checks(self) -> dict[str, ComponentHealth]:
        results = {}
        for name, check in self._checks.items():
            try:
                start = time.time()
                health = check()
                health.latency_ms = (time.time() - start) * 1000
                health.last_check = time.time()
                results[name] = health
            except Exception as e:
                results[name] = ComponentHealth(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check failed: {e}",
                    latency_ms=0.0
                )
        return results

    def overall_status(self) -> HealthStatus:
        checks = self.run_checks()
        if any(c.status == HealthStatus.UNHEALTHY for c in checks.values()):
            return HealthStatus.UNHEALTHY
        if any(c.status == HealthStatus.DEGRADED for c in checks.values()):
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY

    def system_metrics(self) -> dict[str, Any]:
        mem = self._process.memory_info()
        cpu = self._process.cpu_percent()
        return {
            "memory_rss_mb": mem.rss / 1024 / 1024,
            "memory_vms_mb": mem.vms / 1024 / 1024,
            "cpu_percent": cpu,
            "threads": self._process.num_threads(),
            "pid": os.getpid()
        }

    def export_health(self) -> dict[str, Any]:
        checks = self.run_checks()
        return {
            "status": self.overall_status().value,
            "components": {name: {
                "status": c.status.value,
                "message": c.message,
                "latency_ms": c.latency_ms,
                "last_check": c.last_check
            } for name, c in checks.items()},
            "system": self.system_metrics()
        }
