from dataclasses import dataclass, field


@dataclass
class SemanticIndex:
    file_semantics: list = field(default_factory=list)
    vault_concepts: list = field(default_factory=list)
    relations: list = field(default_factory=list)
    patterns: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    normalization_map: dict = field(default_factory=dict)
    file_semantic_map: dict = field(default_factory=dict)
    concept_name_map: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
