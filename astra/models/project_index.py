from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProjectIndex:
    files: list = field(default_factory=list)
    symbols: list = field(default_factory=list)
    dependencies: list = field(default_factory=list)
    semantic_tags: list = field(default_factory=list)
    ast_nodes: list = field(default_factory=list)
    vault_nodes: list = field(default_factory=list)
    file_graph: dict = field(default_factory=dict)
    vault_graph: dict = field(default_factory=dict)
    concept_map: dict = field(default_factory=dict)
    symbol_map: dict = field(default_factory=dict)
    error_files: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
