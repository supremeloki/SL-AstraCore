from dataclasses import dataclass, field
from enum import Enum


class DependencyType(Enum):
    IMPORT = "import"
    CALL = "call"
    INHERITANCE = "inheritance"
    COMPOSITION = "composition"
    IMPLEMENTATION = "implementation"
    REFERENCE = "reference"
    UNKNOWN = "unknown"


@dataclass
class Dependency:
    source_file: str
    source_symbol: str
    target_file: str
    target_symbol: str
    dep_type: DependencyType = DependencyType.UNKNOWN
    line_number: int = 0
    metadata: dict = field(default_factory=dict)
