from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence, Optional

from astra.graph.mutator import GraphMutator
from astra.ir.models import IRContextPack, IRFileNode, IRNode, NodeType, EdgeType, IRFileParseResult
from astra.parser.registry import ParserRegistry
from astra.resolver.import_resolver import resolve_imports_into_edges
from astra.runtime.models import RepoRecord, RepoStatus
from astra.storage.backend import StorageProvider
from astra.context.engine import ContextEngine


class RuntimeOrchestrator:
    """Manages repository lifecycle: register, index, refresh, query context.

    This is the primary entry point for Phase 2 runtime operations.
    No parser/storage/context internals leak through here.
    """

    def __init__(
        self,
        parser_registry: Optional[ParserRegistry] = None,
        metadata_db_path: Optional[str] = None,
    ) -> None:
        self._parser_registry = parser_registry or ParserRegistry()
        self._repos: dict[str, RepoRecord] = {}
        self._metadata_db_path = metadata_db_path or os.path.join(
            os.path.expanduser("~"), ".astra", "runtime.db"
        )

        # Ensure runtime metadata directory exists
        os.makedirs(os.path.dirname(self._metadata_db_path), exist_ok=True)

    def register_repo(
        self,
        root_path: str,
        name: Optional[str] = None,
        backend: str = "duckdb",
    ) -> RepoRecord:
        """Register a repository for indexing."""
        root_path = str(Path(root_path).resolve())
        name = name or Path(root_path).name

        if root_path in self._repos:
            return self._repos[root_path]

        db_path = os.path.join(
            os.path.dirname(self._metadata_db_path),
            f"{name}_{abs(hash(root_path))}.db",
        )

        record = RepoRecord(
            root_path=root_path,
            name=name,
            status=RepoStatus.REGISTERED,
            storage_backend=backend,
            db_path=db_path,
        )
        self._repos[root_path] = record
        return record

    def index_repo(
        self,
        root_path: str,
        file_extensions: Optional[Sequence[str]] = None,
    ) -> RepoRecord:
        """Index a registered repository: scan -> parse -> resolve -> graph -> persist.

        Deterministic, idempotent, incremental-safe.
        """
        record = self._repos.get(root_path)
        if record is None:
            raise ValueError(f"Repository not registered: {root_path}")

        record.status = RepoStatus.INDEXING

        try:
            # 1. Scan repo
            files = self._scan_repo_files(root_path, file_extensions)

            # 2. Parse all files
            parse_results = []
            for file_path in files:
                try:
                    content = Path(file_path).read_text(encoding="utf-8", errors="replace")
                    result = self._parser_registry.parse(file_path, content)
                    if result:
                        parse_results.append(result)
                except Exception:
                    continue

            # 3. Build graph storage
            storage = StorageProvider(
                backend=record.storage_backend,
                db_path=record.db_path,
            ).create()
            storage.connect()
            mutator = GraphMutator(storage)

            # 4. Upsert file nodes
            for result in parse_results:
                if result.file_node:
                    file_node = result.file_node
                    # Normalize to canonical file id
                    canonical_node = IRNode(
                        id=file_node.id,
                        type=file_node.type,
                        name=file_node.name,
                        source=file_node.source,
                        confidence=file_node.confidence,
                        metadata={
                            "file_path": file_node.file_path,
                            "language": file_node.language,
                            "line_count": file_node.line_count,
                            "byte_size": file_node.byte_size,
                            "role": file_node.role.name if hasattr(file_node.role, "name") else str(file_node.role),
                        },
                    )
                    mutator.apply_node_upsert(canonical_node)

            # 5. Resolve imports and create edges
            _, dep_edges = resolve_imports_into_edges(parse_results)

            for edge in dep_edges:
                mutator.apply_edge_upsert(edge)

            # 6. Update record
            record.file_count = len(files)
            record.node_count = storage.node_count()
            record.edge_count = storage.edge_count()
            record.last_indexed = datetime.now(timezone.utc).isoformat()
            record.status = RepoStatus.ACTIVE

            storage.close()

        except Exception as exc:
            record.status = RepoStatus.FAILED
            record.error = str(exc)

        return record

    def refresh_repo(self, root_path: str) -> RepoRecord:
        """Full re-index of a registered repository. Idempotent."""
        return self.index_repo(root_path)

    def query_context(
        self,
        root_path: str,
        seed_node_ids: Sequence[str],
        query_intent: str = "",
        max_tokens: int | None = None,
    ) -> IRContextPack:
        """Generate a context pack from a registered repo's graph."""
        record = self._get_active_record(root_path)

        storage = StorageProvider(
            backend=record.storage_backend,
            db_path=record.db_path,
        ).create()
        storage.connect()

        engine = ContextEngine(storage)
        pack = engine.generate_context_pack(
            query_intent=query_intent,
            seed_nodes=list(seed_node_ids),
            max_tokens=max_tokens,
        )

        storage.close()
        return pack

    def get_repo(self, root_path: str) -> Optional[RepoRecord]:
        return self._repos.get(root_path)

    def list_repos(self) -> Sequence[RepoRecord]:
        return list(self._repos.values())

    def _scan_repo_files(
        self,
        root_path: str,
        file_extensions: Optional[Sequence[str]] = None,
    ) -> list[str]:
        """Scan a repo directory for indexable files.

        Respects .gitignore rules via simple skip logic.
        """
        root = Path(root_path)
        ignore_patterns = {
            ".git", "__pycache__", "node_modules",
            ".venv", "venv", "env", "dist", "build",
            ".egg-info", ".tox", ".mypy_cache",
            ".pytest_cache", "*.pyc", "*.pyo",
        }

        files = []
        for path in root.rglob("*"):
            if path.is_dir():
                continue
            rel = path.relative_to(root)
            parts = rel.parts
            if any(p.startswith(".") and p not in (".gitignore",) for p in parts):
                continue
            if any(p in ignore_patterns for p in parts):
                continue
            if any(str(rel).endswith(s.lstrip("*")) for s in ignore_patterns if s.startswith("*")):
                continue
            if file_extensions:
                if not any(str(path).endswith(ext) for ext in file_extensions):
                    continue
            files.append(str(path))

        return sorted(files)

    def _get_active_record(self, root_path: str) -> RepoRecord:
        record = self._repos.get(root_path)
        if record is None:
            raise ValueError(f"Repository not registered: {root_path}")
        if record.status != RepoStatus.ACTIVE:
            raise RuntimeError(f"Repository not active: {root_path} (status={record.status.value})")
        return record