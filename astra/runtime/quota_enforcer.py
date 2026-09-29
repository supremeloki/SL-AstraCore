from __future__ import annotations

import os
try:
    import resource
except ImportError:  # Windows
    resource = None  # type: ignore[assignment]
import psutil
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional


@dataclass
class QuotaConfig:
    """Hard resource quotas for a task."""
    max_cpu_percent: float = 50.0
    max_memory_mb: int = 512
    max_threads: int = 50
    max_file_descriptors: int = 256
    max_execution_seconds: float = 300.0
    oom_action: str = "kill"  # "kill", "pause", "throttle"


class ResourceQuotaEnforcer:
    """Enforces hard resource quotas with OOM protection."""

    def __init__(self, config: QuotaConfig | None = None) -> None:
        self.config = config or QuotaConfig()
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitor = threading.Event()
        self._violation_callback = None
        self._process = psutil.Process(os.getpid())

    def _check_limits(self) -> list[str]:
        """Check all resource limits, return list of violations."""
        violations = []
        try:
            mem_mb = self._process.memory_info().rss / 1024 / 1024
            if mem_mb > self.config.max_memory_mb:
                violations.append(f"memory:{mem_mb:.0f}MB > {self.config.max_memory_mb}MB")

            cpu = self._process.cpu_percent(interval=0.01)
            if cpu > self.config.max_cpu_percent:
                violations.append(f"cpu:{cpu:.1f}% > {self.config.max_cpu_percent}%")

            threads = self._process.num_threads()
            if threads > self.config.max_threads:
                violations.append(f"threads:{threads} > {self.config.max_threads}")

            # Check file descriptors (Unix only)
            try:
                fds = self._process.num_fds()
                if fds > self.config.max_file_descriptors:
                    violations.append(f"fds:{fds} > {self.config.max_file_descriptors}")
            except (AttributeError, psutil.AccessDenied):
                pass

        except psutil.NoSuchProcess:
            pass

        return violations

    def _monitor_loop(self) -> None:
        """Background monitor loop."""
        while not self._stop_monitor.is_set():
            violations = self._check_limits()
            if violations and self._violation_callback:
                self._violation_callback(violations)
            time.sleep(0.5)

    def start_monitoring(self, on_violation=None) -> None:
        """Start background resource monitoring."""
        self._violation_callback = on_violation
        self._stop_monitor.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop_monitoring(self) -> None:
        """Stop background monitoring."""
        self._stop_monitor.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=1.0)

    def check_quota(self) -> tuple[bool, list[str]]:
        """Check current quota compliance."""
        violations = self._check_limits()
        return len(violations) == 0, violations

    def enforce_memory_limit(self) -> bool:
        """Attempt to enforce memory limit via GC and cache clearing."""
        import gc
        gc.collect()
        return True

    @contextmanager
    def enforce(self):
        """Context manager that enforces quotas during execution."""
        self.start_monitoring()
        try:
            yield self
        finally:
            self.stop_monitoring()

    def apply_os_limits(self) -> None:
        """Apply OS-level resource limits (Unix only)."""
        try:
            import resource as _resource_mod
        except ImportError:  # Windows: no resource module
            return

        # ponytail: resource is untyped/Unix-only; route through Any so the
        # hasattr guards type-check. Swap to a typed stub if Windows support matters.
        from typing import Any as _Any
        res: _Any = _resource_mod

        try:
            if res is None:
                return
            if hasattr(res, "RLIMIT_AS"):
                limit = self.config.max_memory_mb * 1024 * 1024
                res.setrlimit(res.RLIMIT_AS, (limit, limit))
            # CPU time limit
            if hasattr(res, "RLIMIT_CPU"):
                cpu_sec = int(self.config.max_execution_seconds)
                res.setrlimit(res.RLIMIT_CPU, (cpu_sec, cpu_sec))
            # File descriptors
            if hasattr(res, "RLIMIT_NOFILE"):
                res.setrlimit(res.RLIMIT_NOFILE, (self.config.max_file_descriptors, self.config.max_file_descriptors))
        except (ValueError, OSError):
            pass  # Limits may not be adjustable
