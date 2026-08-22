from dataclasses import dataclass, field
from enum import Enum


class EdgeType(Enum):
    DEPENDS_ON = "depends_on"
    IMPLEMENTS = "implements"
    USES = "uses"
    CONFIGURES = "configures"
    REFERENCES = "references"
    CONTRADICTS = "contradicts"
    EXTENDS = "extends"
    BELONGS_TO = "belongs_to"
    IMPACTS = "impacts"
    VALIDATES = "validates"


@dataclass
class GraphEdge:
    from_node: str = ""
    to_node: str = ""
    edge_type: EdgeType = EdgeType.DEPENDS_ON
    weight: float = 1.0
    confidence: float = 0.0
    properties: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
