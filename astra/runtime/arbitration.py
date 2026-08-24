from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ArbitrationDecision(Enum):
    APPROVE = "approve"
    DENY = "deny"
    QUEUE = "queue"
    DELEGATE = "delegate"


@dataclass
class AgentRequest:
    agent_id: str
    task_type: str
    priority: int = 1
    resources: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ArbitrationResult:
    decision: ArbitrationDecision
    reason: str
    assigned_agent: str | None = None
    estimated_wait: float = 0.0


class TaskArbitrator:
    """Arbitrates task execution across multiple agents with conflict resolution."""

    def __init__(self, max_concurrent_per_type: dict[str, int] | None = None) -> None:
        self._agent_loads: dict[str, int] = {}
        self._max_concurrent = max_concurrent_per_type or {}
        self._active_tasks: dict[str, AgentRequest] = {}

    def register_agent(self, agent_id: str) -> None:
        if agent_id not in self._agent_loads:
            self._agent_loads[agent_id] = 0

    def request_execution(self, request: AgentRequest) -> ArbitrationResult:
        # Check per-task-type concurrency limit
        limit = self._max_concurrent.get(request.task_type)
        current = sum(1 for r in self._active_tasks.values() if r.task_type == request.task_type)
        if limit and current >= limit:
            return ArbitrationResult(
                decision=ArbitrationDecision.QUEUE,
                reason=f"Concurrency limit reached for {request.task_type} ({current}/{limit})",
                estimated_wait=5.0
            )

        # Find least loaded agent that can handle this task type
        available_agents = [
            a for a, load in self._agent_loads.items()
            if load < (self._max_concurrent.get("default", 10))
        ]
        if not available_agents:
            return ArbitrationResult(
                decision=ArbitrationDecision.DENY,
                reason="No agents available",
                estimated_wait=10.0
            )

        chosen = min(available_agents, key=lambda a: self._agent_loads[a])
        self._agent_loads[chosen] += 1
        self._active_tasks[request.agent_id] = request

        return ArbitrationResult(
            decision=ArbitrationDecision.APPROVE,
            reason=f"Assigned to {chosen}",
            assigned_agent=chosen
        )

    def release_task(self, agent_id: str) -> None:
        if agent_id in self._active_tasks:
            del self._active_tasks[agent_id]
        if agent_id in self._agent_loads and self._agent_loads[agent_id] > 0:
            self._agent_loads[agent_id] -= 1

    def agent_load(self, agent_id: str) -> int:
        return self._agent_loads.get(agent_id, 0)

    def total_active(self) -> int:
        return len(self._active_tasks)