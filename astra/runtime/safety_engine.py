from __future__ import annotations

from typing import Callable

from astra.runtime.sandbox import ExecutionSandbox
from astra.runtime.quota_enforcer import ResourceQuotaEnforcer
from astra.runtime.timeout_enforcer import TimeoutEnforcer
from astra.runtime.circuit_breaker import CircuitBreaker


class SafetyEngine:
    """Top-level safety surface composing all 3F safety components."""

    def __init__(self) -> None:
        self.sandbox = ExecutionSandbox()
        self.quota = ResourceQuotaEnforcer()
        self.timeout = TimeoutEnforcer()
        self.circuit_breaker = CircuitBreaker()

    def run_safe(self, task_id: str, action: Callable, *args, **kwargs):
        """Execute a task within the full safety stack."""
        with self.sandbox.isolate(), self.quota.enforce(), self.timeout.enforce(task_id, 300):
            if self.circuit_breaker.allow():
                try:
                    return action(*args, **kwargs)
                except Exception as e:
                    self.circuit_breaker.record_failure()
                    raise e
            else:
                raise RuntimeError("Circuit breaker open")
