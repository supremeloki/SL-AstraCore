from dataclasses import dataclass, field


@dataclass
class ArchitectureGraph:
    layers: dict = field(default_factory=dict)
    modules: list = field(default_factory=list)
    boundaries: list = field(default_factory=list)
    data_flow: list = field(default_factory=list)
    entry_points: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class DecisionGraphNode:
    id: str = ""
    decision: str = ""
    reason: str = ""
    impact: str = ""
    related_files: list = field(default_factory=list)
    related_concepts: list = field(default_factory=list)
    timestamp: str = ""
    confidence: float = 0.0


@dataclass
class DecisionGraph:
    decisions: list = field(default_factory=list)
    edges: list = field(default_factory=list)


@dataclass
class PatternGraphNode:
    id: str = ""
    name: str = ""
    pattern_type: str = ""
    occurrences: int = 0
    locations: list = field(default_factory=list)
    affects: list = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class PatternGraph:
    patterns: list = field(default_factory=list)
    edges: list = field(default_factory=list)


@dataclass
class ConflictGraphNode:
    id: str = ""
    source_a: str = ""
    source_b: str = ""
    conflict_type: str = ""
    severity: str = ""
    evidence: str = ""
    confidence: float = 0.0


@dataclass
class ConflictGraph:
    conflicts: list = field(default_factory=list)
    edges: list = field(default_factory=list)


@dataclass
class OrphanReport:
    orphan_nodes: list = field(default_factory=list)
    orphan_concepts: list = field(default_factory=list)
    unconnected_files: list = field(default_factory=list)


@dataclass
class KnowledgeGraph:
    nodes: list = field(default_factory=list)
    edges: list = field(default_factory=list)
    node_index: dict = field(default_factory=dict)
    edge_index: dict = field(default_factory=dict)
    architecture: ArchitectureGraph = field(default_factory=ArchitectureGraph)
    decisions: DecisionGraph = field(default_factory=DecisionGraph)
    patterns: PatternGraph = field(default_factory=PatternGraph)
    conflicts: ConflictGraph = field(default_factory=ConflictGraph)
    orphans: OrphanReport = field(default_factory=OrphanReport)
    entry_points: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
