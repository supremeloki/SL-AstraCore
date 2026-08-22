from dataclasses import dataclass, field
from enum import Enum


class NodeType(Enum):
    FILE = "file"
    FUNCTION = "function"
    CLASS = "class"
    MODULE = "module"
    VAULT_CONCEPT = "vault_concept"
    DECISION = "decision"
    PATTERN = "pattern"
    CONFIG = "config"
    SYMBOL = "symbol"


@dataclass
class GraphNode:
    id: str = ""
    label: str = ""
    node_type: NodeType = NodeType.FILE
    properties: dict = field(default_factory=dict)
    layer: str = ""
    confidence: float = 0.0
    is_orphan: bool = False
    metadata: dict = field(default_factory=dict)
