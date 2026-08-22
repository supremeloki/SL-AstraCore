from dataclasses import dataclass, field
from enum import Enum


class ConceptType(Enum):
    IDEA = "idea"
    RULE = "rule"
    ARCHITECTURE = "architecture"
    DECISION = "decision"
    WARNING = "warning"
    NOTE = "note"


@dataclass
class VaultConcept:
    name: str = ""
    concept_type: ConceptType = ConceptType.NOTE
    meaning: str = ""
    linked_code: list = field(default_factory=list)
    related_concepts: list = field(default_factory=list)
    strength: float = 0.0
    confidence: float = 0.0
    metadata: dict = field(default_factory=dict)
