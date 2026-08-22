from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SemanticTag:
    file_path: str
    purpose: str = ""
    responsibility: str = ""
    business_role: str = ""
    technical_role: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    coupling_score: float = 0.0
    unknowns: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
