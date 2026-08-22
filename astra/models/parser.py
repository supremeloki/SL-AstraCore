from dataclasses import dataclass, field
from enum import Enum


class StructuralKind(Enum):
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    IMPORT = "import"
    CALL = "call"
    HEADING = "heading"
    CONFIG_KEY = "config_key"
    TEXT_BLOCK = "text_block"
    UNKNOWN = "unknown"


@dataclass
class StructuralElement:
    id: str = ""
    file_id: str = ""
    file_path: str = ""
    name: str = ""
    kind: StructuralKind = StructuralKind.UNKNOWN
    line_start: int = 0
    line_end: int = 0
    signature: str = ""
    text: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class DependencySignal:
    source_file: str = ""
    source_element: str = ""
    target: str = ""
    signal_type: str = "reference"
    line_number: int = 0
    confidence: float = 0.0


@dataclass
class ParsedFile:
    file_id: str = ""
    file_path: str = ""
    language: str = ""
    parser_name: str = ""
    elements: list = field(default_factory=list)
    dependencies: list = field(default_factory=list)
    confidence: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class ParserFailure:
    file_path: str = ""
    parser_name: str = ""
    error: str = ""
    recoverable: bool = True


@dataclass
class ParseIndex:
    files: list = field(default_factory=list)
    failures: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def elements(self):
        return [element for parsed in self.files for element in parsed.elements]

    @property
    def dependencies(self):
        return [dep for parsed in self.files for dep in parsed.dependencies]
