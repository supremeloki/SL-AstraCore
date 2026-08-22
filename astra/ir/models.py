from __future__ import annotations

from enum import Enum, auto
from typing import Any, Optional, Protocol, Sequence

from dataclasses import dataclass, field


# ──────────────────────────────────────────────
# Scalar types
# ──────────────────────────────────────────────

Confidence = float
TokenCount = int


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class NodeType(Enum):
    FILE = auto()
    FUNCTION = auto()
    CLASS = auto()
    METHOD = auto()
    MODULE = auto()
    VARIABLE = auto()
    CONSTANT = auto()
    VAULT_CONCEPT = auto()
    DECISION = auto()
    PATTERN = auto()
    CONFLICT = auto()
    CONFIG = auto()


class EdgeType(Enum):
    DEPENDS_ON = auto()
    IMPORTS = auto()
    CALLS = auto()
    REFERENCES = auto()
    IMPLEMENTS = auto()
    EXTENDS = auto()
    BELONGS_TO = auto()
    CONFIGURES = auto()
    IMPACTS = auto()
    CONTRADICTS = auto()
    LINKS_TO = auto()
    VALIDATES = auto()


class SymbolKind(Enum):
    FUNCTION = auto()
    CLASS = auto()
    METHOD = auto()
    VARIABLE = auto()
    CONSTANT = auto()
    DECORATOR = auto()
    TYPE_ALIAS = auto()


class VaultConceptKind(Enum):
    IDEA = auto()
    RULE = auto()
    ARCHITECTURE = auto()
    DECISION = auto()
    WARNING = auto()
    NOTE = auto()
    RFC = auto()
    TODO = auto()
    DESIGN = auto()


class FileRole(Enum):
    ENTRYPOINT = auto()
    SERVICE = auto()
    ADAPTER = auto()
    UTILITY = auto()
    CONFIG = auto()
    DATA = auto()
    TEST = auto()
    UNKNOWN = auto()


class ArchitectureLayer(Enum):
    PRESENTATION = auto()
    APPLICATION = auto()
    DOMAIN = auto()
    INFRASTRUCTURE = auto()
    UTILITIES = auto()
    UNKNOWN = auto()


class Stability(Enum):
    STABLE = auto()
    SEMI_STABLE = auto()
    VOLATILE = auto()


class RiskLevel(Enum):
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()


class TaskType(Enum):
    BUG_FIX = auto()
    FEATURE_ADDITION = auto()
    REFACTOR = auto()
    ANALYSIS = auto()
    ARCHITECTURE_REVIEW = auto()
    DEBUG_TRACE = auto()
    OPTIMIZATION = auto()
    EXPLORATION = auto()


# ──────────────────────────────────────────────
# IR Node models
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class IRNode:
    id: str
    type: NodeType
    name: str
    source: str
    confidence: Confidence = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IRFileNode(IRNode):
    file_path: str = ""
    language: str = ""
    role: FileRole = FileRole.UNKNOWN
    line_count: int = 0
    byte_size: int = 0
    is_binary: bool = False
    is_vault: bool = False
    architecture_layer: ArchitectureLayer = ArchitectureLayer.UNKNOWN
    stability: Stability = Stability.STABLE
    risk_level: RiskLevel = RiskLevel.LOW


@dataclass(frozen=True)
class IRFunctionNode(IRNode):
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0
    parent_class: str = ""
    is_async: bool = False
    is_method: bool = False
    is_private: bool = False


@dataclass(frozen=True)
class IRClassNode(IRNode):
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0
    bases: tuple[str, ...] = ()
    is_abstract: bool = False
    method_count: int = 0


@dataclass(frozen=True)
class IRMethodNode(IRNode):
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0
    parent_class: str = ""
    is_async: bool = False
    is_static: bool = False
    is_property: bool = False
    is_private: bool = False


@dataclass(frozen=True)
class IRModuleNode(IRNode):
    file_path: str = ""
    children: tuple[str, ...] = ()
    line_count: int = 0


@dataclass(frozen=True)
class IRVaultConceptNode(IRNode):
    concept_type: VaultConceptKind = VaultConceptKind.NOTE
    file_path: str = ""
    linked_code_paths: tuple[str, ...] = ()
    related_concepts: tuple[str, ...] = ()
    strength: Confidence = 0.0


@dataclass(frozen=True)
class IRDecisionNode(IRNode):
    decision: str = ""
    reason: str = ""
    impact: str = ""
    file_path: str = ""
    related_files: tuple[str, ...] = ()
    related_concepts: tuple[str, ...] = ()


@dataclass(frozen=True)
class IRPatternNode(IRNode):
    pattern_type: str = ""
    occurrences: int = 0
    locations: tuple[str, ...] = ()
    is_positive: bool = True


@dataclass(frozen=True)
class IRConflictNode(IRNode):
    source_a: str = ""
    source_b: str = ""
    conflict_type: str = ""
    severity: RiskLevel = RiskLevel.MEDIUM
    evidence: str = ""


@dataclass(frozen=True)
class IRConfigNode(IRNode):
    file_path: str = ""
    format: str = ""
    keys: tuple[str, ...] = ()


# ──────────────────────────────────────────────
# IR Edge models
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class IREdge:
    from_node: str
    to_node: str
    type: EdgeType
    weight: float = 1.0
    confidence: Confidence = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


# ──────────────────────────────────────────────
# Symbol / Dependency / Vault link
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class IRSymbol:
    name: str
    kind: SymbolKind
    file_path: str
    line_start: int = 0
    line_end: int = 0
    parent: str = ""
    is_exported: bool = False
    is_private: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IRDependency:
    source_file: str
    target_module: str
    kind: str = ""
    line: int = 0
    is_resolved: bool = False
    resolved_target: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IRVaultLink:
    note_path: str
    target_type: str = ""
    target_id: str = ""
    strength: Confidence = 0.0
    link_kind: str = ""


# ──────────────────────────────────────────────
# Aggregate models
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class IRProjectIndex:
    project_root: str = ""
    file_count: int = 0
    total_lines: int = 0
    total_bytes: int = 0
    languages: dict[str, int] = field(default_factory=dict)
    vault_note_count: int = 0
    config_count: int = 0
    binary_count: int = 0
    ignored_count: int = 0
    files: tuple[IRFileNode, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IRFileParseResult:
    file_path: str = ""
    language: str = ""
    file_node: Optional[IRFileNode] = None
    symbols: tuple[IRSymbol, ...] = ()
    dependencies: tuple[IRDependency, ...] = ()
    vault_concepts: tuple[IRVaultConceptNode, ...] = ()
    vault_links: tuple[IRVaultLink, ...] = ()
    parse_errors: tuple[str, ...] = ()
    confidence: Confidence = 0.0


# ──────────────────────────────────────────────
# Context Pack (output of Context Engine)
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class ContextNodeRef:
    node_id: str
    node_type: NodeType
    name: str
    file_path: str
    snippet: str = ""
    relevance_score: float = 0.0


@dataclass(frozen=True)
class ContextEdgeRef:
    from_node: str
    to_node: str
    edge_type: EdgeType
    weight: float = 1.0


@dataclass(frozen=True)
class IRContextPack:
    task_summary: str = ""
    task_type: TaskType = TaskType.ANALYSIS
    query_intent: str = ""
    nodes: tuple[ContextNodeRef, ...] = ()
    edges: tuple[ContextEdgeRef, ...] = ()
    vault_context: tuple[IRVaultConceptNode, ...] = ()
    decisions: tuple[IRDecisionNode, ...] = ()
    patterns: tuple[IRPatternNode, ...] = ()
    conflicts: tuple[IRConflictNode, ...] = ()
    required_files: tuple[str, ...] = ()
    dependency_summary: tuple[str, ...] = ()
    hidden_risks: tuple[str, ...] = ()
    total_tokens: TokenCount = 0
    token_budget: TokenCount = 0
    confidence: Confidence = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
