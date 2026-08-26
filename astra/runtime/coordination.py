from __future__ import annotations

from typing import Any

from astra.runtime.scheduler import AdaptiveScheduler, Priority
from astra.runtime.resources import ResourceManager, ResourceQuota
from astra.runtime.arbitration import TaskArbitrator, AgentRequest, ArbitrationDecision, ArbitrationResult
from astra.runtime.queue_balancer import QueueBalancer


class CoordinationEngine:
    """Top-level coordination surface composing all 3E components."""

    def __init__(
        self,
        max_queue_depth: int = 1000,
        rebalance_interval: float = 10.0,
        default_quota: ResourceQuota | None = None,
    ) -> None:
        self.scheduler = AdaptiveScheduler(max_queue_depth)
        self.resources = ResourceManager()
        self.arbitration = TaskArbitrator()
        self.balancer = QueueBalancer(rebalance_interval)
        self._default_quota = default_quota or ResourceQuota()

    def submit_task(
        self,
        task_id: str,
        action: str,
        agent_id: str,
        priority: Priority = Priority.NORMAL,
        delay: float = 0.0,
        payload: dict[str, Any] | None = None,
        quota: ResourceQuota | None = None,
    ) -> tuple[str | None, ArbitrationResult]:
        """Full coordination flow: schedule -> resource check -> arbitrate -> assign worker."""
        # 1. Schedule
        try:
            self.scheduler.enqueue(
                task_id=task_id,
                action=action,
                priority=priority,
                delay=delay,
                payload=payload or {},
            )
        except RuntimeError as e:
            return None, ArbitrationResult(
                decision=ArbitrationDecision.DENY,
                reason=str(e),
                assigned_agent=None
            )

        # 2. Resource check
        q = quota or self._default_quota
        can_accept, reason = self.resources.can_accept_task(q)
        if not can_accept:
            self.scheduler.remove(task_id)
            return None, ArbitrationResult(
                decision=ArbitrationDecision.DENY,
                reason=f"Resource check failed: {reason}",
                assigned_agent=None
            )

        # 3. Arbitration
        request = AgentRequest(
            agent_id=agent_id,
            task_type=action,
            priority=priority.value,
            resources={"cpu": q.max_cpu_percent, "memory": q.max_memory_mb},
        )
        arb_result = self.arbitration.request_execution(request)
        if arb_result.decision.value != "approve":
            self.scheduler.remove(task_id)
            return None, arb_result

        # 4. Worker assignment
        worker = self.balancer.select_worker()
        if not worker:
            self.scheduler.remove(task_id)
            self.arbitration.release_task(agent_id)
            return None, ArbitrationResult(
                decision=ArbitrationDecision.DENY,
                reason="No workers available",
                assigned_agent=None
            )

        # Assign quota
        self.resources.assign_quota(task_id, q)
        return worker, arb_result

    def complete_task(
        self,
        task_id: str,
        agent_id: str,
        latency_ms: float,
        success: bool = True
    ) -> None:
        """Called when task finishes (success or failure)."""
        self.scheduler.mark_completed(task_id) if success else self.scheduler.mark_failed(task_id, "failed")
        self.resources.release_quota(task_id)
        self.arbitration.release_task(agent_id)
        # Find which worker completed it - simplified: just report to balancer
        for w in self.balancer._workers:
            if self.balancer._workers[w].queue_depth > 0:
                self.balancer.task_completed(w, latency_ms)
                break

    def get_stats(self) -> dict[str, Any]:
        return {
            "scheduler": {
                "queue_depth": self.scheduler.queue_depth(),
                "backpressure": self.scheduler.backpressure(),
                "completed": self.scheduler.completed_count(),
                "failed": self.scheduler.failed_count(),
            },
            "resources": {
                "memory_mb": self.resources.current_memory_mb(),
                "cpu_percent": self.resources.current_cpu_percent(),
            },
            "arbitration": {
                "active_tasks": self.arbitration.total_active(),
                "agent_loads": {k: v for k, v in self.arbitration._agent_loads.items() if v > 0},
            },
            "balancer": self.balancer.get_stats(),
        }