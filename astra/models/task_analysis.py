from dataclasses import dataclass, field
from enum import Enum


class TaskType(Enum):
    BUG_FIX = "bug_fix"
    FEATURE_ADDITION = "feature_addition"
    REFACTOR = "refactor"
    ANALYSIS = "analysis"
    ARCHITECTURE_REVIEW = "architecture_review"
    DEBUG_TRACE = "debug_trace"
    OPTIMIZATION = "optimization"


@dataclass
class TaskAnalysis:
    task: str = ""
    task_type: TaskType = TaskType.ANALYSIS
    target_scope: list = field(default_factory=list)
    affected_domain: str = ""
    keywords: list = field(default_factory=list)
    confidence: float = 0.0
    metadata: dict = field(default_factory=dict)
