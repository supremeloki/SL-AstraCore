from dataclasses import dataclass, field
from enum import Enum


class ConflictSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConflictType(Enum):
    LOGIC = "logic"
    ARCHITECTURE = "architecture"
    CONFIG = "config"
    NAMING = "naming"
    VERSIONING = "versioning"


@dataclass
class Conflict:
    source_a: str = ""
    source_b: str = ""
    conflict_type: ConflictType = ConflictType.LOGIC
    severity: ConflictSeverity = ConflictSeverity.LOW
    description: str = ""
    confidence: float = 0.0
    metadata: dict = field(default_factory=dict)
