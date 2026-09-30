from __future__ import annotations

import hashlib
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence, Optional

from astra.core.logger import get_logger
from astra.graph.enrichment import enrich_graph
from astra.graph.mutator import GraphMutator
from astra.ir.models import (
    ContextEdgeRef,
    ContextNodeRef,
    EdgeType,
    IRContextPack,
    IREdge,
    IRNode,
    IRSymbol,
    NodeType,
    SymbolKind,
)
from astra.models.graph_node import GraphNode as GraphNodeModel
from astra.storage.backend import StorageBackend
from astra.parser.registry import build_default_parser_registry, ParserRegistry
from astra.resolver.import_resolver import resolve_imports_into_edges
from astra.runtime.models import RepoRecord, RepoStatus
from astra.storage.backend import StorageProvider
from astra.context.engine import ContextEngine

logger = get_logger("astra.runtime.orchestrator")


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
        self._parser_registry = parser_registry or build_default_parser_registry()
        self._repos: dict[str, RepoRecord] = {}
        # DuckDB allows one writer per file. Indexing and querying both open the
        # same per-repo database, so a second writer would fail with an opaque
        # "Catalog write-write conflict" and be reported as a failed repo. One
        # lock per repo, shared by writers and readers, prevents that.
        self._repo_locks: dict[str, threading.Lock] = {}
        astra_home = os.environ.get("ASTRA_HOME") or os.path.join(
            os.path.expanduser("~"), ".astra"
        )
        self._metadata_db_path = metadata_db_path or os.path.join(
            astra_home, "runtime.db"
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

        # Deterministic per-repo DB path: stable across processes (hash() is salted).
        digest = hashlib.sha256(root_path.encode("utf-8")).hexdigest()[:16]
        db_path = os.path.join(
            os.path.dirname(self._metadata_db_path),
            f"{name}_{digest}.db",
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

        with self._lock_for(root_path):
            return self._index_locked(record, file_extensions)

    def _index_locked(
        self,
        record: RepoRecord,
        file_extensions: Optional[Sequence[str]],
    ) -> RepoRecord:
        root_path = record.root_path
        record.status = RepoStatus.INDEXING
        record.warnings = []

        if not Path(root_path).exists():
            record.status = RepoStatus.FAILED
            record.error = f"Repository root does not exist: {root_path}"
            return record

        storage = None
        try:
            # 1. Scan repo
            files = self._scan_repo_files(root_path, file_extensions)

            # 2. Parse all files. A file that fails to read (sharing violation from
            # an editor/AV/git, transient IO) is NOT the same as a deleted file —
            # it must keep its existing graph nodes so a later index can recover.
            parse_results = []
            unreadable_files: list[str] = []
            for file_path in files:
                try:
                    content = Path(file_path).read_text(encoding="utf-8", errors="replace")
                except OSError as exc:
                    unreadable_files.append(file_path)
                    record.warnings.append(f"unreadable: {file_path} ({exc})")
                    continue
                try:
                    result = self._parser_registry.parse(file_path, content)
                except Exception as exc:
                    unreadable_files.append(file_path)
                    record.warnings.append(f"parse failed: {file_path} ({exc})")
                    continue
                if result:
                    parse_results.append(result)

            # 3. Build graph storage
            storage = StorageProvider(
                backend=record.storage_backend,
                db_path=record.db_path,
            ).create()
            storage.connect()
            mutator = GraphMutator(storage)

            # 4. Normalize file nodes and keep path->id map for edge endpoints
            nodes_to_upsert = []
            symbol_nodes: list[IRNode] = []
            path_to_node_id = {}
            for result in parse_results:
                if result.file_node:
                    file_node = result.file_node
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
                    nodes_to_upsert.append(canonical_node)
                    path_to_node_id[file_node.file_path] = file_node.id

                    # 4b. Promote parsed symbols (functions/classes) to real graph
                    # nodes. Without this the graph is files-only and every context
                    # pack can only ever name files, never point at a function.
                    for symbol in result.symbols:
                        symbol_nodes.append(
                            IRNode(
                                id=_symbol_node_id(file_node.id, symbol),
                                type=_symbol_node_type(symbol),
                                name=symbol.name,
                                source=f"symbol:{file_node.language or 'unknown'}",
                                confidence=file_node.confidence,
                                metadata={
                                    "file_path": file_node.file_path,
                                    "file_node_id": file_node.id,
                                    "kind": symbol.kind.name,
                                    "line_start": symbol.line_start,
                                    "line_end": symbol.line_end,
                                    "language": file_node.language,
                                },
                            )
                        )

            # 5. Resolve imports; resolver works in root-relative space, map
            # back to canonical file: node IDs.
            _, dep_edges = resolve_imports_into_edges(parse_results)
            edges_to_upsert = [
                IREdge(
                    from_node=path_to_node_id[edge.from_node],
                    to_node=path_to_node_id[edge.to_node],
                    type=edge.type,
                    weight=edge.weight,
                    confidence=edge.confidence,
                    metadata=edge.metadata,
                )
                for edge in dep_edges
                if edge.from_node in path_to_node_id and edge.to_node in path_to_node_id
            ]

            # 5b. Enrichment: pattern + conflict nodes/edges (best-effort).
            file_nodes_for_enrichment = [
                result.file_node for result in parse_results if result.file_node
            ]
            extra_nodes, extra_edges, enrich_warnings = enrich_graph(file_nodes_for_enrichment)
            record.warnings.extend(enrich_warnings)
            fresh_file_ids = {n.id for n in nodes_to_upsert}
            extra_edges = [
                e for e in extra_edges
                if e.from_node and e.to_node and (
                    not e.to_node.startswith("file:") or e.to_node in fresh_file_ids
                )
            ]
            nodes_to_upsert.extend(extra_nodes)
            edges_to_upsert.extend(extra_edges)

            # 5c. Register symbol nodes and their BELONGS_TO edges to their file.
            nodes_to_upsert.extend(symbol_nodes)
            edges_to_upsert.extend(
                IREdge(
                    from_node=node.id,
                    to_node=node.metadata["file_node_id"],
                    type=EdgeType.BELONGS_TO,
                    weight=0.6,
                    confidence=node.confidence,
                )
                for node in symbol_nodes
            )

            # 6. Drop nodes for files actually removed since last index (cascades
            # edges), then persist everything in one atomic batch. Files that merely
            # failed to read this run are excluded from the delete set — along with
            # every node that hangs off them (symbol nodes, enrichment nodes) — so a
            # transient lock cannot silently destroy a file's subgraph.
            fresh_ids = {n.id for n in nodes_to_upsert}
            existing_ids = storage.get_node_ids()
            preserved_file_ids = {f"file:{path}" for path in unreadable_files}
            preserved_ids = {nid for nid in existing_ids if nid in preserved_file_ids}
            preserved_ids |= {
                nid
                for nid in existing_ids
                if any(nid.startswith(f"{fid}::") for fid in preserved_file_ids)
            }
            stale_ids = sorted(existing_ids - fresh_ids - preserved_ids)

            # 5d. Edges between surviving nodes also go stale: remove an import
            # from a file and the graph kept reporting the dependency forever.
            # Node deletion cascades, so only edges whose endpoints both survive
            # need an explicit delete. An edge touching a file we could not read
            # this run is kept: we have no fresh view of it, so it is not stale.
            preserved_prefixes = tuple(f"{fid}::" for fid in preserved_file_ids)
            upserted_keys = {(x.from_node, x.to_node, x.type.name) for x in edges_to_upsert}
            surviving = fresh_ids | preserved_ids

            def _touches_unreadable(node_id: str) -> bool:
                if node_id in preserved_file_ids:
                    return True
                # startswith(()) is always True, so only test when non-empty.
                return bool(preserved_prefixes) and node_id.startswith(preserved_prefixes)

            stale_edges = sorted(
                (e.from_node, e.to_node, e.type)
                for e in storage.get_all_edges()
                if (e.from_node, e.to_node, e.type.name) not in upserted_keys
                and e.from_node in surviving
                and e.to_node in surviving
                and not _touches_unreadable(e.from_node)
                and not _touches_unreadable(e.to_node)
            )

            mutator.apply_batch(
                nodes_to_delete=stale_ids,
                nodes_to_upsert=nodes_to_upsert,
                edges_to_upsert=edges_to_upsert,
                edges_to_delete=stale_edges,
            )

            # 7. Update record
            record.file_count = len(parse_results) + len(unreadable_files)
            record.node_count = storage.node_count()
            record.edge_count = storage.edge_count()
            record.last_indexed = datetime.now(timezone.utc).isoformat()
            record.status = RepoStatus.ACTIVE
            record.error = None

        except Exception as exc:
            record.status = RepoStatus.FAILED
            # str(exc) alone lost the traceback, so a DuckDB catalog conflict
            # surfaced as a bare one-liner with no way to trace the cause.
            record.error = f"{type(exc).__name__}: {exc}"
            logger.exception("indexing failed for %s", root_path)
        finally:
            if storage is not None:
                storage.close()

        return record

    def _lock_for(self, root_path: str) -> threading.Lock:
        lock = self._repo_locks.get(root_path)
        if lock is None:
            # Setdefault makes creation atomic without holding a second lock on
            # the dict itself, which the callers of this method already hold.
            lock = self._repo_locks.setdefault(root_path, threading.Lock())
        return lock

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
        """Generate a context pack from a registered repo's graph.

        With no explicit seeds, the task-aware pipeline (task analysis ->
        strategy -> ranking -> token budget) selects seeds from the query.
        """
        record = self._get_record(root_path)

        with self._lock_for(root_path):
            # Re-read the status now that the writer has released: a query that
            # arrived mid-index used to fail outright instead of reading the
            # graph the index just wrote.
            if record.status != RepoStatus.ACTIVE:
                raise RuntimeError(
                    f"Repository not active: {root_path} (status={record.status.value})"
                )
            storage = StorageProvider(
                backend=record.storage_backend,
                db_path=record.db_path,
            ).create()
            storage.connect()

            try:
                if seed_node_ids:
                    engine = ContextEngine(storage)
                    return engine.generate_context_pack(
                        query_intent=query_intent,
                        seed_nodes=list(seed_node_ids),
                        max_tokens=max_tokens,
                    )

                return self._build_task_context_pack(record, storage, query_intent, max_tokens)
            finally:
                storage.close()

    def _build_task_context_pack(
        self,
        record: RepoRecord,
        storage: StorageBackend,
        query_intent: str,
        max_tokens: int | None,
    ) -> IRContextPack:
        from astra.models.graph_node import node_type_from_ir
        from astra.models.knowledge_graph import KnowledgeGraph
        from astra.context.context_engine import ContextEngine as TaskContextEngine

        kg = KnowledgeGraph()
        for n in storage.get_all_nodes():
            props = dict(n.metadata or {})
            file_path = getattr(n, "file_path", "") or props.get("file_path", "")
            if n.type == NodeType.FILE and not file_path:
                file_path = n.id.removeprefix("file:")
            if file_path:
                props["file_path"] = file_path
            gn = GraphNodeModel(
                id=n.id,
                label=n.name or n.id,
                node_type=node_type_from_ir(n.type),
                confidence=n.confidence,
                properties=props,
            )
            kg.nodes.append(gn)
            kg.node_index[gn.id] = gn
        for e in storage.get_all_edges():
            kg.edges.append(e)

        engine = TaskContextEngine(kg)
        if max_tokens and max_tokens > 0:
            engine._token_budget.set_budget(max_tokens)
        _analysis, _pack, _deps, _risks = engine.build_pack(query_intent)

        def _file_path_of(node: dict) -> str:
            explicit = node.get("file_path") or ""
            if explicit:
                return explicit
            node_id = node.get("id", "")
            return node_id.removeprefix("file:") if node_id.startswith("file:") else ""

        def _snippet_for(node: dict, char_limit: int = 0) -> str:
            """Read the real source this node points at.

            A symbol node carries line_start/line_end, so an agent gets the function
            body; a file node gets its head. This is what makes a context pack
            usable by an agent instead of a bare list of filenames.
            """
            node_id = node.get("id", "")
            graph_node = kg.node_index.get(node_id)
            props = graph_node.properties if graph_node is not None else {}
            path = node.get("file_path") or props.get("file_path") or ""
            if not path and node_id.startswith("file:"):
                path = node_id.removeprefix("file:")
            if not path:
                return ""
            source_file = Path(path)
            if not source_file.is_absolute():
                source_file = Path(record.root_path) / path
            try:
                lines = source_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                return ""
            if not lines:
                return ""
            start = int(props.get("line_start") or 0)
            if start > 0:
                end = min(int(props.get("line_end") or start), start + _SNIPPET_MAX_LINES - 1)
                body = lines[start - 1:end]
                header = f"# {node.get('label', source_file.name)} — {source_file.name}:{start}-{end}"
                text = "\n".join([header, *body])
            else:
                text = "\n".join(lines[:_SNIPPET_MAX_LINES])
            if char_limit and len(text) > char_limit:
                text = text[:char_limit].rsplit("\n", 1)[0] + "\n# … truncated to fit token budget"
            return text

        def _ir_node_type(node_id: str) -> NodeType:
            legacy = node_type_from_ir(kg.node_index[node_id].node_type)
            return NodeType[legacy.name]

        # 2.3 Snippets must fit the caller's budget. Each snippet is estimated
        # (~4 chars/token) and truncated to the remaining allowance, so a pack
        # with real code can never exceed the token budget it reports.
        effective_budget = max_tokens if max_tokens and max_tokens > 0 else _DEFAULT_TOKEN_BUDGET
        snippet_allowance = int(effective_budget * 0.7)
        snippet_chars = max(0, snippet_allowance * 4)
        spent = 0
        nodes_with_snippets: list[ContextNodeRef] = []
        for n in _pack.relevant_nodes:
            if not isinstance(n, dict):
                continue
            remaining = snippet_chars - spent
            snippet = _snippet_for(n, char_limit=remaining) if remaining > 200 else ""
            spent += len(snippet)
            nodes_with_snippets.append(
                ContextNodeRef(
                    node_id=n["id"],
                    node_type=_ir_node_type(n["id"]) if n["id"] in kg.node_index else NodeType.FILE,
                    name=n.get("label", ""),
                    file_path=_file_path_of(n),
                    snippet=snippet,
                    relevance_score=float(n.get("relevance", 1.0)),
                )
            )
        nodes_ref = tuple(nodes_with_snippets)
        selected_ids = {nr.node_id for nr in nodes_ref}
        edges_ref = tuple(
            ContextEdgeRef(
                from_node=critical["from"],
                to_node=critical["to"],
                edge_type=EdgeType.DEPENDS_ON,
            )
            for critical in _pack.critical_dependencies
            if critical["from"] in selected_ids and critical["to"] in selected_ids
        )

        return IRContextPack(
            task_summary=_analysis.task,
            task_type=_analysis.task_type,
            query_intent=query_intent,
            nodes=nodes_ref,
            edges=edges_ref,
            required_files=tuple(_pack.required_files),
            dependency_summary=tuple(str(d) for d in _pack.critical_dependencies[:20]),
            hidden_risks=tuple(_risks.medium_risk_nodes[:10]),
            total_tokens=_pack.token_estimate,
            token_budget=effective_budget,
            confidence=_analysis.confidence,
        )

    def get_repo(self, root_path: str) -> Optional[RepoRecord]:
        return self._repos.get(root_path)

    def remove_repo(self, root_path: str) -> bool:
        """Unregister a repo. Returns False if it was never registered."""
        record = self._repos.pop(root_path, None)
        return record is not None

    def list_repos(self) -> Sequence[RepoRecord]:
        return list(self._repos.values())

    def _scan_repo_files(
        self,
        root_path: str,
        file_extensions: Optional[Sequence[str]] = None,
    ) -> list[str]:
        """Scan a repo directory for indexable files.

        Respects built-in ignores plus simple root/.gitignore rules
        (dir names, *.ext globs, leading paths).
        """
        root = Path(root_path)
        ignore_patterns = {
            ".git", "__pycache__", "node_modules",
            ".venv", "venv", "env", "dist", "build",
            ".egg-info", ".tox", ".mypy_cache",
            ".pytest_cache", "*.pyc", "*.pyo",
        }
        gitignore_rules = [r.replace("\\", "/").rstrip("/") for r in self._parse_gitignore(root / ".gitignore")]
        ignore_names = ignore_patterns | {r for r in gitignore_rules if "/" not in r}
        ignore_suffixes = tuple(
            s[1:] for s in list(ignore_names) + gitignore_rules if s.startswith("*")
        )
        # Leading-path rules like "src/generated" match as rel-prefix.
        ignore_prefixes = tuple(r + "/" for r in gitignore_rules if "/" in r)

        files = []
        for path in root.rglob("*"):
            if path.is_dir():
                continue
            rel = path.relative_to(root)
            rel_str = str(rel).replace("\\", "/")
            parts = rel.parts
            if any(p.startswith(".") and p not in (".gitignore",) for p in parts):
                continue
            if any(p in ignore_names for p in parts):
                continue
            if ignore_suffixes and rel_str.endswith(ignore_suffixes):
                continue
            if any(rel_str.startswith(prefix) for prefix in ignore_prefixes):
                continue
            if file_extensions and not any(str(path).endswith(ext) for ext in file_extensions):
                continue
            files.append(str(path))

        return sorted(files)

    @staticmethod
    def _parse_gitignore(gitignore_path: Path) -> list[str]:
        """Extract simple skip rules from a .gitignore file."""
        if not gitignore_path.is_file():
            return []
        rules = []
        try:
            for line in gitignore_path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("!"):
                    continue
                rules.append(line.lstrip("/"))
        except OSError:
            return []
        return rules

    def _get_record(self, root_path: str) -> RepoRecord:
        record = self._repos.get(root_path)
        if record is None:
            raise ValueError(f"Repository not registered: {root_path}")
        return record

    def _get_active_record(self, root_path: str) -> RepoRecord:
        record = self._repos.get(root_path)
        if record is None:
            raise ValueError(f"Repository not registered: {root_path}")
        if record.status != RepoStatus.ACTIVE:
            raise RuntimeError(f"Repository not active: {root_path} (status={record.status.value})")
        return record


_SNIPPET_MAX_LINES = 40
_DEFAULT_TOKEN_BUDGET = 32000
_SYMBOL_KIND_TO_NODE_TYPE = {
    SymbolKind.FUNCTION: NodeType.FUNCTION,
    SymbolKind.CLASS: NodeType.CLASS,
    SymbolKind.METHOD: NodeType.METHOD,
    SymbolKind.VARIABLE: NodeType.VARIABLE,
    SymbolKind.CONSTANT: NodeType.CONSTANT,
    SymbolKind.TYPE_ALIAS: NodeType.CLASS,
}


def _symbol_node_type(symbol: IRSymbol) -> NodeType:
    return _SYMBOL_KIND_TO_NODE_TYPE.get(symbol.kind, NodeType.FUNCTION)


def _symbol_node_id(file_node_id: str, symbol: IRSymbol) -> str:
    """Stable, collision-resistant id for a symbol node.

    A file can define the same name twice (methods in different classes), so the
    line number participates in the identity.
    """
    return f"{file_node_id}::symbol:{symbol.name}:{symbol.line_start}"
