from __future__ import annotations
from typing import Protocol

from astra.ir.models import IRContextPack
from astra.planner.models import ExecutionPlan

class PlannerProtocol(Protocol):
    """Planner contract only. No execution logic."""

    def plan(
        self,
        task_description: str,
        context: IRContextPack,
    ) -> ExecutionPlan:
        ...
