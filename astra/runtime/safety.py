"""3F Safety Layer — Execution Isolation & Safety.

Comprehensive safety for SL-AstraCore runtime:
  - Execution Sandbox (filesystem + network isolation)
  - Resource Quota Enforcement (hard caps, OOM protection)
  - Cancellation Propagation (cooperative + timeout-based)
  - Timeout Enforcement (per-task deadlines with escalation)
  - Circuit Breaker (failure domain isolation)
  - Safety Engine (unified safety surface)
"""

from astra.runtime.sandbox import ExecutionSandbox, SandboxConfig
from astra.runtime.quota_enforcer import ResourceQuotaEnforcer, QuotaConfig
from astra.runtime.cancellation import (
    CancellationContext, CancelledError,
    cancellation_scope, timeout_scope, cancel_all
)
from astra.runtime.timeout_enforcer import TimeoutEnforcer, TimeoutExceeded
from astra.runtime.circuit_breaker import CircuitBreaker
from astra.runtime.safety_engine import SafetyEngine
