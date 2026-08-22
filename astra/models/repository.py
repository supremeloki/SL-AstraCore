from dataclasses import dataclass, field
from enum import Enum

from astra.models.file_node import FileCategory, FileNode


class FileKind(Enum):
    TEXT = "text"
    BINARY = "binary"
    DIRECTORY = "directory"
    SYMLINK = "symlink"
    UNKNOWN = "unknown"


@dataclass
class FileMetadata:
    id: str
    path: str
    rel_path: str
    name: str
    extension: str = ""
    category: FileCategory = FileCategory.UNKNOWN
    kind: FileKind = FileKind.UNKNOWN
    language: str | None = None
    size_bytes: int = 0
    hash_value: str = ""
    hash_algorithm: str = "sha256"
    modified_at: float = 0.0
    is_hidden: bool = False
    is_symlink: bool = False
    is_binary: bool = False
    encoding: str = "utf-8"
    lines_count: int = 0
    metadata: dict = field(default_factory=dict)

    def to_file_node(self):
        return FileNode(
            path=self.path,
            rel_path=self.rel_path,
            category=self.category,
            language=self.language,
            extension=self.extension,
            size_bytes=self.size_bytes,
            hash_sha256=self.hash_value if self.hash_algorithm == "sha256" else "",
            lines_count=self.lines_count,
            last_modified=self.modified_at,
            encoding=self.encoding,
            metadata={
                **self.metadata,
                "id": self.id,
                "kind": self.kind.value,
                "hash_algorithm": self.hash_algorithm,
                "is_hidden": self.is_hidden,
                "is_symlink": self.is_symlink,
                "is_binary": self.is_binary,
            },
        )


@dataclass
class TreeNode:
    path: str
    name: str
    node_type: str = "directory"
    children: list = field(default_factory=list)
    file_id: str = ""


@dataclass
class RepositoryTree:
    root: str = ""
    nodes: dict = field(default_factory=dict)


@dataclass
class LanguageSummary:
    by_language: dict = field(default_factory=dict)
    by_extension: dict = field(default_factory=dict)
    binary_files: int = 0
    text_files: int = 0


@dataclass
class ScanFailure:
    path: str
    phase: str
    error: str


@dataclass
class ScanMetadata:
    root_path: str = ""
    files_seen: int = 0
    files_indexed: int = 0
    directories_seen: int = 0
    ignored_paths: int = 0
    skipped_large_files: int = 0
    failures_count: int = 0
    resumed: bool = False
    checkpoint_path: str = ""
    deterministic: bool = True
    metadata: dict = field(default_factory=dict)


@dataclass
class RepositoryIndex:
    root_path: str = ""
    files: list = field(default_factory=list)
    tree: RepositoryTree = field(default_factory=RepositoryTree)
    language_summary: LanguageSummary = field(default_factory=LanguageSummary)
    metadata: ScanMetadata = field(default_factory=ScanMetadata)
    failures: list = field(default_factory=list)

    def to_file_nodes(self):
        return [file_meta.to_file_node() for file_meta in self.files]
