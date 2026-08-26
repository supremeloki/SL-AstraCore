from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Protocol, Sequence

from astra.ir.models import IRContextPack, RiskLevel


class ExecutionMode(Enum):
    ANALYSIS = auto()
    PLANNING = auto()
    EXECUTION = auto()
    RECOVERY = auto()


class StepStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


@dataclass(frozen=True)
class ExecutionStep:
    step_id: str
    action_type: str
    target_files: tuple[str, ...] = ()
    required_context: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    risk_level: RiskLevel = RiskLevel.LOW
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionPlan:
    execution_id: str
    mode: ExecutionMode
    steps: tuple[ExecutionStep, ...] = ()
    ordering_strategy: str = ""
    fallback_plan: tuple[str, ...] = ()
    confidence: float = 0.0


@dataclass(frozen=True)
class ExecutionTrace:
    step_id: str
    status: StepStatus
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    logs: tuple[str, ...] = ()


class RuntimeOrchestrator(Protocol):
    def plan(self, context_pack: IRContextPack) -> ExecutionPlan: ...


class ToolAdapter(Protocol):
    name: str

    def supports(self, action_type: str) -> bool: ...


class ToolRegistry(Protocol):
    def register(self, tool: ToolAdapter) -> None: ...

    def unregister(self, name: str) -> None: ...

    def get(self, name: str) -> ToolAdapter: ...


class ValidationEngine(Protocol):
    def validate(self, plan: ExecutionPlan) -> bool: ...


class RecoveryEngine(Protocol):
    def recover(
        self,
        trace: Sequence[ExecutionTrace],
    ) -> ExecutionPlan: ...
