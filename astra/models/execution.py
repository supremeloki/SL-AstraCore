from dataclasses import dataclass, field
from enum import Enum


class ChangeType(Enum):
    CREATE_FILE = "create_file"
    MODIFY_FILE = "modify_file"
    DELETE_FILE = "delete_file"
    REFACTOR_MODULE = "refactor_module"
    INTEGRATE_SYSTEM = "integrate_system"


@dataclass
class ChangeSpec:
    file_path: str = ""
    change_type: ChangeType = ChangeType.MODIFY_FILE
    after: str = ""
    reason: str = ""
    before: str | None = None
    dependencies_affected: list = field(default_factory=list)
    risk_level: str = "low"
    confidence: float = 0.0


@dataclass
class Patch:
    file_path: str = ""
    change_type: ChangeType = ChangeType.MODIFY_FILE
    before: str | None = None
    after: str = ""
    reason: str = ""
    dependencies_affected: list = field(default_factory=list)
    risk_level: str = "low"
    confidence: float = 0.0
    validation_errors: list = field(default_factory=list)


@dataclass
class FileChangeMap:
    created: list = field(default_factory=list)
    modified: list = field(default_factory=list)
    deleted: list = field(default_factory=list)
    refactored: list = field(default_factory=list)
    integrated: list = field(default_factory=list)


@dataclass
class DependencyImpactReport:
    direct: list = field(default_factory=list)
    upstream: list = field(default_factory=list)
    downstream: list = field(default_factory=list)
    breaking_changes: list = field(default_factory=list)
    circular_risks: list = field(default_factory=list)


@dataclass
class RollbackPlan:
    steps: list = field(default_factory=list)
    recovery_notes: list = field(default_factory=list)


@dataclass
class ExecutionResult:
    patch_set: list = field(default_factory=list)
    file_change_map: FileChangeMap = field(default_factory=FileChangeMap)
    dependency_impact: DependencyImpactReport = field(default_factory=DependencyImpactReport)
    risk_analysis: list = field(default_factory=list)
    rollback_plan: RollbackPlan = field(default_factory=RollbackPlan)
    execution_log: list = field(default_factory=list)
    applied: bool = False
    confidence: float = 0.0
