from dataclasses import dataclass, field
from enum import Enum


class PatternType(Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


@dataclass
class Pattern:
    name: str = ""
    pattern_type: PatternType = PatternType.POSITIVE
    occurrences: int = 0
    locations: list = field(default_factory=list)
    confidence: float = 0.0
    metadata: dict = field(default_factory=dict)
