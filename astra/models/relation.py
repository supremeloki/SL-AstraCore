from dataclasses import dataclass, field
from enum import Enum


class RelationType(Enum):
    DEPENDS_ON = "depends_on"
    IMPLEMENTS = "implements"
    EXTENDS = "extends"
    CONTRADICTS = "contradicts"
    CONFIGURES = "configures"
    DOCUMENTS = "documents"
    REFERENCES = "references"


@dataclass
class Relation:
    from_node: str = ""
    to_node: str = ""
    rel_type: RelationType = RelationType.DEPENDS_ON
    weight: float = 1.0
    metadata: dict = field(default_factory=dict)
