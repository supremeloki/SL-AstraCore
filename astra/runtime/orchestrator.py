from __future__ import annotations

import hashlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    FileRole,
    IRContextPack,
    IRDependency,
    IREdge,
    IRFileNode,
    IRFileParseResult,
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
from astra.runtime.repo_lock import file_lock
from astra.storage.backend import StorageProvider
from astra.context.engine import ContextEngine

logger = get_logger("astra.runtime.orchestrator")


def _symbol_kind(raw) -> SymbolKind:
    """The stored symbol kind, which is a name in metadata, not an enum.

    VARIABLE is the fallback because every SymbolKind member is a concrete
    thing a parser can find, and an unrecognised name is closer to a variable
    than to a class.
    """
    if isinstance(raw, SymbolKind):
        return raw
    try:
        return SymbolKind[str(raw)]
    except KeyError:
        return SymbolKind.VARIABLE


def _read_text(path: str) -> str:
    """Module level so the thread pool does not capture `self` per task."""
    return Path(path).read_text(encoding="utf-8", errors="replace")


def _key(root_path: str) -> str:
    """The dict key for a repository.

    One spelling per path, so registering a path and then looking it up by a
    short name, a relative path or a trailing slash finds the same record.
    Only the Windows runners use 8.3 names in temp paths, so only they hit
    this — as "Repository not registered" on a repo that was registered.
    """
    return str(Path(root_path).resolve())


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
        self._document_frequency: dict[str, tuple] = {}
        # path -> (mtime_ns, size) per repo, so a re-index only parses
        # what changed.
        self._file_stamps: dict[str, dict[str, tuple[int, int]]] = {}
        self._graph_cache: dict[str, tuple] = {}
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
        root_path = _key(root_path)
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
        record = self._get_record(root_path)
        root_path = record.root_path

        # Both locks: the threading.Lock serialises threads in this process,
        # the file lock serialises processes. DuckDB's own lock is per-process,
        # so two servers or a server and a CLI run both need the file.
        with self._lock_for(root_path), file_lock(record.db_path):
            return self._index_locked(record, file_extensions)

    def _index_locked(
        self,
        record: RepoRecord,
        file_extensions: Optional[Sequence[str]],
    ) -> RepoRecord:
        root_path = record.root_path
        record.status = RepoStatus.INDEXING
        record.warnings = []
        # The file set is about to change, so the cached term counts and the
        # cached graph are both stale.
        self._document_frequency.pop(record.root_path, None)
        self._graph_cache.pop(record.root_path, None)

        if not Path(root_path).exists():
            record.status = RepoStatus.FAILED
            record.error = f"Repository root does not exist: {root_path}"
            return record

        storage = None
        try:
            # 1. Scan the repository, then work out what actually changed.
            #
            # A file whose mtime and size are unchanged has the same content,
            # so parsing it can only produce the nodes it already has. The
            # previous attempt at skipping them left stale edges behind,
            # because an import edge is only recomputed when both of its
            # endpoints are parsed — the fix was to stop skipping the files
            # entirely, which was correct and slow. Here the unchanged files
            # are still skipped for parsing, and their dependency lists are
            # read back from the graph so the resolver sees both endpoints.
            all_files = self._scan_repo_files(root_path, file_extensions)

            previous = self._file_stamps.get(record.root_path, {})
            current: dict[str, tuple[int, int]] = {}
            changed: list[str] = []
            for file_path in all_files:
                try:
                    info = os.stat(file_path)
                except OSError:
                    changed.append(file_path)
                    continue
                stamp = (info.st_mtime_ns, info.st_size)
                current[file_path] = stamp
                if previous.get(file_path) != stamp:
                    changed.append(file_path)
            skipped_paths = [
                p for p in all_files
                if p not in set(changed)
            ]
            if previous:
                record.warnings.append(
                    f"incremental: {len(changed)} of {len(all_files)} files changed"
                )
            files = changed

            # 2. Parse all files. A file that fails to read (sharing violation from
            # an editor/AV/git, transient IO) is NOT the same as a deleted file —
            # it must keep its existing graph nodes so a later index can recover.
            #
            # Read in a thread pool: the cost is opening the file, and on
            # Windows an antivirus filter puts that on a syscall that releases
            # the GIL, so threads overlap it. Parsing stays single-threaded —
            # the Python AST is the CPU-bound half and threads would only add
            # contention around the interpreter's own lock.
            contents: dict[str, str | None] = {}
            # Skipped files are opened too, purely to notice a lock. An index
            # that silently keeps a stale file because its mtime had not
            # changed would leave the user believing the graph is current.
            # The content is discarded; only the failure matters.
            to_open = list(files) + list(skipped_paths)
            with ThreadPoolExecutor(max_workers=16) as pool:
                futures = {pool.submit(_read_text, f): f for f in to_open}
                for future in as_completed(futures):
                    file_path = futures[future]
                    try:
                        contents[file_path] = future.result()
                    except OSError as exc:
                        contents[file_path] = None
                        record.warnings.append(f"unreadable: {file_path} ({exc})")

            parse_results = []
            unreadable_files: list[str] = [
                p for p in skipped_paths if contents.get(p) is None
            ]
            for file_path in files:
                content = contents.get(file_path)
                if content is None:
                    unreadable_files.append(file_path)
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
                            # The import list travels with the file node, so an
                            # incremental run can rebuild this file's edges
                            # without parsing it. Without it a skipped file
                            # contributes no dependencies and every edge
                            # touching it silently disappears.
                            "dependencies": [
                                {
                                    "target_module": dep.target_module,
                                    "kind": dep.kind,
                                    "line": dep.line,
                                    "level": dep.level,
                                }
                                for dep in result.dependencies
                            ],
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
            #
            # The resolver needs every file's dependency list, because an edge
            # is only recomputed when both of its endpoints are parsed. An
            # incremental run has the changed files freshly parsed and the rest
            # already in the graph, so the unchanged ones are read back and
            # handed over as lightweight results — parsing them again is what
            # made incremental indexing pointless, and dropping them is what
            # left stale edges behind last time this was tried.
            resolution_input = list(parse_results)
            if skipped_paths:
                reconstructed = self._reconstruct_for_resolution(
                    storage, skipped_paths
                )
                resolution_input.extend(reconstructed)
                # A skipped file produces edges too, so its node id has to be
                # resolvable. Without this the edge out of it was dropped by
                # the lookup below and re-adding an import silently did nothing.
                for result in reconstructed:
                    if result.file_node:
                        path_to_node_id[result.file_node.file_path] = result.file_node.id
            _, dep_edges = resolve_imports_into_edges(resolution_input)
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

            # 6. Drop nodes for files removed since the last index, cascades
            # edges, then persist everything in one atomic batch. Only a file
            # that could not be read this run is preserved: a file that was
            # read is fully described by nodes_to_upsert, so anything left over
            # from its previous shape — a symbol at an old line number, an
            # import that was deleted — has to go.
            fresh_ids = {n.id for n in nodes_to_upsert}
            existing_ids = storage.get_node_ids()
            # Two kinds of file keep their nodes: one this run could not read, and one
            # it deliberately did not re-parse. Without the second an
            # incremental run deleted the whole repository, because the write
            # is a full replacement rather than a merge.
            preserved_file_ids = {f"file:{path}" for path in unreadable_files} | {
                f"file:{path}" for path in skipped_paths
            }
            preserved_ids = {nid for nid in existing_ids if nid in preserved_file_ids}
            preserved_ids |= {
                nid
                for nid in existing_ids
                if any(nid.startswith(f"{fid}::") for fid in preserved_file_ids)
            }
            # Analytic nodes describe the repository rather than one file, so
            # they are not covered by the per-file skip. They are rebuilt on
            # every run that re-parsed anything, and kept when it did not.
            preserved_ids |= {
                nid
                for nid in existing_ids
                if nid.startswith("pattern:") or nid.startswith("conflict:")
            } if not files else set()
            stale_ids = sorted(existing_ids - fresh_ids - preserved_ids)

            # 5d. Edges between surviving nodes also go stale: remove an import
            # from a file and the graph kept reporting the dependency forever.
            # Node deletion cascades, so only edges whose endpoints both survive
            # need an explicit delete. An edge touching a file we could not read
            # this run is kept: we have no fresh view of it, so it is not stale.
            upserted_keys = {(x.from_node, x.to_node, x.type.name) for x in edges_to_upsert}
            surviving = fresh_ids | preserved_ids

            # Only a file this run could NOT read blocks an edge from being
            # stale. A file that was merely skipped still has its dependency
            # list on record, so its edges are rebuilt like everyone else's —
            # exempting it here is what kept a deleted import in the graph.
            unreadable_file_ids = {f"file:{path}" for path in unreadable_files}
            unreadable_prefixes = tuple(f"{fid}::" for fid in unreadable_file_ids)

            def _touches_unreadable(node_id: str) -> bool:
                if node_id in unreadable_file_ids:
                    return True
                # startswith(()) is always True, so only test when non-empty.
                return bool(unreadable_prefixes) and node_id.startswith(unreadable_prefixes)

            # An edge whose endpoints this run did not rebuild was not rebuilt — the
            # resolver only produces import edges, so a skipped file has no
            # fresh BELONGS_TO or IMPLEMENTS edges to re-assert. Deleting them
            # strands the surviving nodes; they are not stale, they are simply
            # untouched this run.
            def _between_skipped(edge) -> bool:
                return (
                    edge.from_node in preserved_ids and edge.to_node in preserved_ids
                )

            stale_edges = sorted(
                (e.from_node, e.to_node, e.type)
                for e in storage.get_all_edges()
                if (e.from_node, e.to_node, e.type.name) not in upserted_keys
                and e.from_node in surviving
                and e.to_node in surviving
                and not _touches_unreadable(e.from_node)
                and not _touches_unreadable(e.to_node)
                and not _between_skipped(e)
            )

            mutator.apply_batch(
                nodes_to_delete=stale_ids,
                nodes_to_upsert=nodes_to_upsert,
                edges_to_upsert=edges_to_upsert,
                edges_to_delete=stale_edges,
            )

            # 7. Update record
            # A file this run could not read or parse keeps no stamp, so the next
            # run tries it again — the failure may have been an editor's lock
            # or an antivirus filter rather than anything about the file.
            for failed in unreadable_files:
                current.pop(failed, None)
            self._file_stamps[record.root_path] = current
            record.file_count = len(current)
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

        # A query that arrives while the first index is still queued behind the
        # lock used to raise "Repository not active (status=registered)": the
        # lock serialises the two, but nothing told the query the index was
        # coming. Indexing here is idempotent, so the wait is the fix.
        if record.status in (RepoStatus.REGISTERED, RepoStatus.UNKNOWN):
            self.index_repo(root_path)

        with self._lock_for(root_path), file_lock(record.db_path):
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

        # Reuse the graph between queries. Rebuilding it meant a fresh DuckDB
        # connection plus a full row-to-node conversion on every question: 141ms
        # of the 180ms query, and 2.1s for the first one. It is invalidated by
        # node_count, so an index in between is picked up.
        cached = self._graph_cache.get(record.root_path)
        node_count = storage.node_count()
        if cached is not None and cached[0] == node_count:
            kg = cached[1]
        else:
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
            self._graph_cache[record.root_path] = (node_count, kg)

        # Reuse the term counts: the graph is rebuilt every query, but the file
        # set it describes has not changed since the last index.
        frequency, files_indexed = self._document_frequency.get(record.root_path, (None, None))

        engine = TaskContextEngine(
            kg, document_frequency=frequency, files_indexed=files_indexed
        )
        self._document_frequency[record.root_path] = engine._ranking.carried_over()
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
        # Spend the snippet budget on the best matches first. relevant_nodes
        # arrives in set order, so the budget was going to whichever node
        # happened to be iterated first and the strongest matches came back
        # with an empty snippet.
        ordered = sorted(
            (entry for entry in _pack.relevant_nodes if isinstance(entry, dict)),
            key=lambda entry: float(entry.get("relevance", 0.0)),
            reverse=True,
        )
        for entry in ordered:
            remaining = snippet_chars - spent
            # Cap per node. Without it the first few matches each took the whole
            # remaining allowance and the budget ran out at rank 19, so a file
            # ranked 20th arrived in the pack with no source at all.
            per_node = min(remaining, _SNIPPET_PER_NODE_CHARS)
            snippet = _snippet_for(entry, char_limit=per_node) if per_node > 200 else ""
            spent += len(snippet)
            nodes_with_snippets.append(
                ContextNodeRef(
                    node_id=entry["id"],
                    node_type=(
                        _ir_node_type(entry["id"])
                        if entry["id"] in kg.node_index
                        else NodeType.FILE
                    ),
                    name=entry.get("label", ""),
                    file_path=_file_path_of(entry),
                    snippet=snippet,
                    relevance_score=float(entry.get("relevance", 1.0)),
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
        return self._repos.get(_key(root_path))

    def remove_repo(self, root_path: str) -> bool:
        """Unregister a repo. Returns False if it was never registered."""
        record = self._repos.pop(_key(root_path), None)
        return record is not None

    def list_repos(self) -> Sequence[RepoRecord]:
        return list(self._repos.values())

    def _reconstruct_for_resolution(
        self,
        storage,
        paths: Sequence[str],
    ) -> list:
        """Rebuild lightweight parse results for files this run did not parse.

        The import resolver needs each file's dependency list, and only that.
        The dependencies were recorded on the symbol nodes when the file was
        indexed, so they can be read back instead of re-parsing the source —
        which is the difference between an incremental run and a full one.

        Symbols come back too, because _common_root reads file nodes and the
        resolver matches module names against them; a result with only a file
        node and no dependencies would resolve nothing.
        """
        if not paths:
            return []
        wanted = {f"file:{p}" for p in paths}
        by_id = {node.id: node for node in storage.get_all_nodes()}
        # Storage returns plain IRNode rows; a file is an IRFileNode, which is
        # a subclass carrying file_path, language and role. Those three live in
        # metadata once flattened into a row, so read them back from there.
        def _as_file_node(node):
            metadata = dict(node.metadata or {})
            file_path = getattr(node, "file_path", "") or metadata.get("file_path", "")
            if not file_path:
                file_path = node.id.removeprefix("file:")
            language = getattr(node, "language", "") or metadata.get("language", "")
            role = getattr(node, "role", None)
            if role is None:
                try:
                    role = FileRole(metadata.get("role", FileRole.UNKNOWN.value))
                except ValueError:
                    role = FileRole.UNKNOWN
            return IRFileNode(
                id=node.id,
                type=node.type,
                name=node.name,
                source=node.source,
                confidence=node.confidence,
                file_path=file_path,
                language=language,
                role=role,
                # The recorded import list rides along, and it is the whole
                # reason this function exists: without it a skipped file
                # rebuilds no edges and every import touching it disappears.
                metadata=metadata,
            )

        file_by_id = {
            node_id: _as_file_node(node)
            for node_id, node in by_id.items()
            if node_id in wanted
        }

        # Symbols hang off their file through a BELONGS_TO edge; group them so
        # one pass over the edges serves every file.
        symbols_by_file: dict[str, list] = {}
        for edge in storage.get_all_edges():
            if edge.type != EdgeType.BELONGS_TO or edge.to_node not in wanted:
                continue
            symbol = by_id.get(edge.from_node)
            if symbol is not None:
                symbols_by_file.setdefault(edge.to_node, []).append(symbol)

        rebuilt: list = []
        for file_id in wanted:
            node = file_by_id.get(file_id)
            if node is None:
                continue
            file_path = node.file_path
            file_metadata = dict(node.metadata or {})

            symbols: list[IRSymbol] = []
            for symbol in symbols_by_file.get(file_id, ()):
                properties = dict(symbol.metadata or {})
                # A stored symbol row is an IRNode; kind and the line numbers
                # live in metadata once flattened into a graph_nodes row.
                symbols.append(
                    IRSymbol(
                        name=symbol.name,
                        kind=_symbol_kind(properties.get("kind")),
                        file_path=file_path,
                        line_start=int(properties.get("line_start", 0) or 0),
                        line_end=int(properties.get("line_end", 0) or 0),
                        parent=properties.get("parent", ""),
                    )
                )

            # The import list was recorded on the file node when this file was
            # indexed; it is what lets its edges be rebuilt without its source.
            dependencies = [
                IRDependency(
                    source_file=file_path,
                    target_module=entry.get("target_module", ""),
                    kind=entry.get("kind", ""),
                    line=int(entry.get("line", 0) or 0),
                    level=int(entry.get("level", 0) or 0),
                )
                for entry in (file_metadata.get("dependencies") or [])
                if entry.get("target_module")
            ]

            rebuilt.append(
                IRFileParseResult(
                    file_path=file_path,
                    language=node.language,
                    file_node=node,
                    symbols=tuple(symbols),
                    dependencies=tuple(dependencies),
                )
            )
        return rebuilt

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
        # os.scandir reports is_dir()/is_file() from the directory entry, so no
        # extra stat per path. Path.rglob("*") followed by is_dir() cost one
        # stat per candidate — 20k of them on an 80-file tree, because every
        # directory was visited and then re-queried.
        stack = [root]
        while stack:
            current = stack.pop()
            try:
                entries = list(os.scandir(current))
            except OSError:
                continue
            for entry in entries:
                name = entry.name
                if name.startswith(".") and name != ".gitignore":
                    continue
                if name in ignore_names:
                    continue
                try:
                    is_dir = entry.is_dir()
                except OSError:
                    continue
                rel = os.path.relpath(entry.path, root).replace("\\", "/")
                if is_dir:
                    if not any(rel == p or rel.startswith(p) for p in ignore_prefixes):
                        stack.append(Path(entry.path))
                    continue
                if ignore_suffixes and rel.endswith(ignore_suffixes):
                    continue
                if any(rel.startswith(prefix) for prefix in ignore_prefixes):
                    continue
                if file_extensions and not rel.endswith(tuple(file_extensions)):
                    continue
                files.append(entry.path)

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
        record = self._repos.get(_key(root_path))
        if record is None:
            raise ValueError(f"Repository not registered: {root_path}")
        return record

    def _get_active_record(self, root_path: str) -> RepoRecord:
        record = self._repos.get(_key(root_path))
        if record is None:
            raise ValueError(f"Repository not registered: {root_path}")
        if record.status != RepoStatus.ACTIVE:
            raise RuntimeError(f"Repository not active: {root_path} (status={record.status.value})")
        return record


_SNIPPET_MAX_LINES = 40
# ~600 tokens of source per node: enough for a function body, small enough
# that 30 nodes still fit a 4k budget.
_SNIPPET_PER_NODE_CHARS = 2400
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
