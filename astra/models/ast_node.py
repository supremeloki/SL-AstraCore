from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ASTNode:
    file_path: str = ""
    node_type: str = ""
    node_kind: str = ""
    text: str = ""
    line_start: int = 0
    line_end: int = 0
    col_start: int = 0
    col_end: int = 0
    children: list = field(default_factory=list)
    parent_node: Optional["ASTNode"] = None
    metadata: dict = field(default_factory=dict)
