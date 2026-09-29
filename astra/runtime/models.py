from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional



class RepoStatus(Enum):
    UNKNOWN = "unknown"
    REGISTERED = "registered"
    INDEXING = "indexing"
    ACTIVE = "active"
    FAILED = "failed"


@dataclass
class RepoRecord:
    root_path: str
    name: str
    status: RepoStatus = RepoStatus.UNKNOWN
    storage_backend: str = "duckdb"
    db_path: str = ""
    file_count: int = 0
    node_count: int = 0
    edge_count: int = 0
    last_indexed: Optional[str] = None
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)
