from dataclasses import dataclass, field
from enum import Enum


class RuntimeMode(Enum):
    DASHBOARD = "dashboard"
    ASK_PROJECT = "ask_project"
    TASK_EXECUTION = "task_execution"
    DEBUG_TRACE = "debug_trace"


@dataclass
class ProjectHealth:
    stability: str = "unknown"
    files_total: int = 0
    graph_nodes: int = 0
    graph_edges: int = 0
    high_risk_count: int = 0
    conflict_count: int = 0
    orphan_count: int = 0
    confidence: float = 0.0


@dataclass
class DashboardView:
    project_health: ProjectHealth = field(default_factory=ProjectHealth)
    architecture_state: dict = field(default_factory=dict)
    dependency_state: dict = field(default_factory=dict)
    risk_hotspots: list = field(default_factory=list)
    conflict_overview: list = field(default_factory=list)
    knowledge_coverage: dict = field(default_factory=dict)
    entry_points: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class BrainAnswer:
    question: str = ""
    answer: str = ""
    used_nodes: list = field(default_factory=list)
    used_decisions: list = field(default_factory=list)
    conflicts_considered: list = field(default_factory=list)
    required_files: list = field(default_factory=list)
    confidence: float = 0.0
    unknowns: list = field(default_factory=list)


@dataclass
class ExecutionPlan:
    task: str = ""
    steps: list = field(default_factory=list)
    affected_nodes: list = field(default_factory=list)
    required_files: list = field(default_factory=list)
    risks: list = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class DebugTraceReport:
    task: str = ""
    root_candidates: list = field(default_factory=list)
    propagation_path: list = field(default_factory=list)
    impacted_modules: list = field(default_factory=list)
    conflict_nodes: list = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class RuntimeResponse:
    mode: RuntimeMode = RuntimeMode.DASHBOARD
    dashboard: DashboardView | None = None
    answer: BrainAnswer | None = None
    execution_plan: ExecutionPlan | None = None
    debug_trace: DebugTraceReport | None = None
    context_pack: object | None = None
    metadata: dict = field(default_factory=dict)
