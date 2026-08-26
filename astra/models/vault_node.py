from dataclasses import dataclass, field


@dataclass
class VaultNode:
    file_path: str = ""
    title: str = ""
    content: str = ""
    frontmatter: dict = field(default_factory=dict)
    wikilinks: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    concepts: list = field(default_factory=list)
    decisions: list = field(default_factory=list)
    architecture_notes: list = field(default_factory=list)
    linked_code_modules: list = field(default_factory=list)
    is_daily_note: bool = False
    is_template: bool = False
    metadata: dict = field(default_factory=dict)
