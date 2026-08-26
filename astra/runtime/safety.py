"""3F Safety Layer — Execution Isolation & Safety.

Comprehensive safety for SL-AstraCore runtime:
  - Execution Sandbox (filesystem + network isolation)
  - Resource Quota Enforcement (hard caps, OOM protection)
  - Cancellation Propagation (cooperative + timeout-based)
  - Timeout Enforcement (per-task deadlines with escalation)
  - Circuit Breaker (failure domain isolation)
  - Safety Engine (unified safety surface)
"""

