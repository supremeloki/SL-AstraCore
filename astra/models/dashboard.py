from dataclasses import dataclass, field
from enum import Enum


class DashboardEventType(Enum):
    SCAN_STARTED = "SCAN_STARTED"
    SCAN_PROGRESS = "SCAN_PROGRESS"
    GRAPH_UPDATED = "GRAPH_UPDATED"
    CONTEXT_BUILT = "CONTEXT_BUILT"
    EXECUTION_STARTED = "EXECUTION_STARTED"
    EXECUTION_STEP_COMPLETED = "EXECUTION_STEP_COMPLETED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    EXECUTION_REPLAYED = "EXECUTION_REPLAYED"


@dataclass
class DashboardEvent:
    event_type: DashboardEventType
    payload: dict = field(default_factory=dict)
    timestamp: float = 0.0


@dataclass
class DashboardSystem:
    graph_view: dict = field(default_factory=dict)
    context_view: dict = field(default_factory=dict)
    execution_view: dict = field(default_factory=dict)
    telemetry: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
