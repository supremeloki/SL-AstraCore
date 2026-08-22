from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Sequence

class StepStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()

@dataclass(frozen=True)
class TaskStep:
    id: str
    description: str
    tool: str
    params: dict[str, Any]
    dependencies: Sequence[str] = ()
    status: StepStatus = StepStatus.PENDING

@dataclass(frozen=True)
class ExecutionPlan:
    task_id: str
    steps: Sequence[TaskStep]
    context_requirements: Sequence[str] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
