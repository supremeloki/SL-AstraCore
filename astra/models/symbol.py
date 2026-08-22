from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SymbolKind(Enum):
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    VARIABLE = "variable"
    IMPORT = "import"
    CALL = "call"
    MODULE = "module"
    INTERFACE = "interface"
    STRUCT = "struct"
    ENUM = "enum"
    CONSTANT = "constant"
    TYPE = "type"
    PROPERTY = "property"
    PARAMETER = "parameter"
    UNKNOWN = "unknown"


@dataclass
class Symbol:
    name: str
    kind: SymbolKind = SymbolKind.UNKNOWN
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0
    col_start: int = 0
    col_end: int = 0
    parent: Optional[str] = None
    signature: str = ""
    body: str = ""
    metadata: dict = field(default_factory=dict)
