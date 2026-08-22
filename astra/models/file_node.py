from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class FileCategory(Enum):
    SOURCE = "source"
    KNOWLEDGE = "knowledge"
    CONFIG = "config"
    DATA = "data"
    SYSTEM = "system"
    DOCUMENT = "document"
    ASSET = "asset"
    UNKNOWN = "unknown"


class FileStatus(Enum):
    UNREAD = "unread"
    READING = "reading"
    READ = "read"
    PARSED = "parsed"
    INDEXED = "indexed"
    ERROR = "error"


@dataclass
class FileNode:
    path: str
    rel_path: str
    category: FileCategory = FileCategory.UNKNOWN
    language: Optional[str] = None
    extension: str = ""
    size_bytes: int = 0
    status: FileStatus = FileStatus.UNREAD
    hash_sha256: str = ""
    lines_count: int = 0
    last_modified: float = 0.0
    encoding: str = "utf-8"
    metadata: dict = field(default_factory=dict)
