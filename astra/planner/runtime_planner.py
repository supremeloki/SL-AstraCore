from __future__ import annotations

from collections import deque
from typing import Optional, Sequence

from astra.core.logger import get_logger
from astra.ir.models import IRContextPack
from astra.planner.models import ExecutionPlan, TaskStep, StepStatus

logger = get_logger("astra.planner.runtime_planner")


class RuntimeTaskPlanner:
    """Phase 3B: Concrete planner that generates execution plans from context.

    Consumes IRContextPack (from Cognitive Core) and produces an ExecutionPlan
    with ordered TaskSteps. No graph mutation, no execution — pure planning.
    """

    def __init__(self, max_steps: int = 20) -> None:
        self._max_steps = max_steps

    def plan(
        self,
        task_description: str,
        context: IRContextPack,
        tools: Optional[Sequence[str]] = None,
    ) -> ExecutionPlan:
        steps: list[TaskStep] = []
        step_idx = 0

        # Step 1: Analyze context
        steps.append(TaskStep(
            id=f"step-{step_idx}",
            description=f"Analyze context for: {task_description}",
            tool="context_analyzer",
            params={"task_summary": context.task_summary, "task_type": context.task_type.value},
            dependencies=(),
            status=StepStatus.PENDING,
        ))
        step_idx += 1

        # Step 2: Resolve required files
        if context.required_files:
            steps.append(TaskStep(
                id=f"step-{step_idx}",
                description="Resolve and load required files",
                tool="file_resolver",
                params={"files": list(context.required_files)},
                dependencies=(steps[0].id,),
                status=StepStatus.PENDING,
            ))
            step_idx += 1

        # Step 3: Map dependency graph
        if context.edges:
            steps.append(TaskStep(
                id=f"step-{step_idx}",
                description="Map dependency graph from context edges",
                tool="dependency_mapper",
                params={"edge_count": len(context.edges)},
                dependencies=(steps[0].id,),
                status=StepStatus.PENDING,
            ))
            step_idx += 1

        # Step 4: Identify risks
        if context.hidden_risks:
            steps.append(TaskStep(
                id=f"step-{step_idx}",
                description="Identify and categorize hidden risks",
                tool="risk_analyzer",
                params={"risks": list(context.hidden_risks)},
                dependencies=(steps[0].id,),
                status=StepStatus.PENDING,
            ))
            step_idx += 1

        # Step 5: Execute task with agent adapter
        deps = [s.id for s in steps]
        steps.append(TaskStep(
            id=f"step-{step_idx}",
            description=f"Execute task via agent adapter: {task_description}",
            tool="agent_adapter",
            params={"task": task_description, "tools": list(tools) if tools else []},
            dependencies=tuple(deps),
            status=StepStatus.PENDING,
        ))
        step_idx += 1

        # Step 6: Validate results
        steps.append(TaskStep(
            id=f"step-{step_idx}",
            description="Validate execution results against expected schema",
            tool="validator",
            params={"confidence_threshold": context.confidence},
            dependencies=(steps[-1].id,),
            status=StepStatus.PENDING,
        ))
        step_idx += 1

        # Step 7: Merge results back to graph (if applicable)
        steps.append(TaskStep(
            id=f"step-{step_idx}",
            description="Merge execution results back to knowledge graph",
            tool="graph_mutator",
            params={},
            dependencies=(steps[-1].id,),
            status=StepStatus.PENDING,
        ))

        return ExecutionPlan(
            task_id=f"plan-{hash(task_description) & 0xFFFFFFFF:08x}",
            steps=tuple(steps[:self._max_steps]),
            context_requirements=tuple(context.required_files),
            metadata={
                "task_description": task_description,
                "task_type": context.task_type.value,
                "context_confidence": context.confidence,
                "step_count": len(steps),
            },
        )
