from dataclasses import dataclass, field


@dataclass
class ContextPack:
    task: str = ""
    relevant_nodes: list = field(default_factory=list)
    relevant_concepts: list = field(default_factory=list)
    relevant_decisions: list = field(default_factory=list)
    relevant_patterns: list = field(default_factory=list)
    critical_dependencies: list = field(default_factory=list)
    conflicts_to_watch: list = field(default_factory=list)
    required_files: list = field(default_factory=list)
    hidden_risks: list = field(default_factory=list)
    confidence: float = 0.0
    token_estimate: int = 0
    task_type: str = "analysis"
    metadata: dict = field(default_factory=dict)
