from dataclasses import dataclass, field
from enum import Enum


class NodeType(Enum):
    FILE = "file"
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    MODULE = "module"
    VARIABLE = "variable"
    CONSTANT = "constant"
    VAULT_CONCEPT = "vault_concept"
    DECISION = "decision"
    PATTERN = "pattern"
    CONFLICT = "conflict"
    CONFIG = "config"
    SYMBOL = "symbol"

_IR_TO_GRAPH_NODE_TYPE = {
    1: NodeType.FILE,
    2: NodeType.FUNCTION,
    3: NodeType.CLASS,
    4: NodeType.METHOD,
    5: NodeType.MODULE,
    6: NodeType.VARIABLE,
    7: NodeType.CONSTANT,
    8: NodeType.VAULT_CONCEPT,
    9: NodeType.DECISION,
    10: NodeType.PATTERN,
    11: NodeType.CONFLICT,
    12: NodeType.CONFIG,
}

def node_type_from_ir(ir_type: object) -> "NodeType":
    if hasattr(ir_type, "name"):
        try:
            return NodeType[ir_type.name]
        except KeyError:
            pass
    if isinstance(ir_type, int):
        mapped = _IR_TO_GRAPH_NODE_TYPE.get(ir_type)
        if mapped is not None:
            return mapped
    return NodeType.FILE


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
