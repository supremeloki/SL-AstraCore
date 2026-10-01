"""SL-AstraCore Dashboard — Real API backed by Core + Runtime."""

from pathlib import Path
import asyncio
import os
import secrets
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from astra.runtime.orchestrator import RuntimeOrchestrator
from astra.runtime.metrics import MetricsCollector
from astra.runtime.event_bus import EventBus, RuntimeEvent
from astra.runtime.journal import ExecutionJournal
from astra.runtime.replay_engine import ReplayEngine
from astra.runtime.health import HealthDiagnostics
from astra.runtime.telemetry import TelemetryEngine
from astra.runtime.tracing import Tracer
from astra.parser.registry import build_default_parser_registry

app = FastAPI(title="SL-AstraCore", docs_url="/docs")

# ── Runtime ────────────────────────────────────────────────────────────
# The default registry wires all 12 language adapters (Python, JS/TS, Markdown
# plus the tree-sitter set). Hand-rolling one here silently dropped Go/Rust/Java/
# C/C++/C#/Ruby/PHP from every index the dashboard produced.
_registry = build_default_parser_registry()
_orchestrator = RuntimeOrchestrator(parser_registry=_registry)
_metrics = MetricsCollector()
_event_bus = EventBus()
_health = HealthDiagnostics()
_telemetry = TelemetryEngine(service_name="sl-astracore-dashboard")
_tracer = Tracer()

_EXPLORER_MAX_DEPTH = 12
_EXPLORER_MAX_ENTRIES = 5000

# Journal for execution mutations (patch applies); replayable via /api/executions/replay.
_astra_home = os.environ.get("ASTRA_HOME") or os.path.join(os.path.expanduser("~"), ".astra")
_journal = ExecutionJournal(os.path.join(_astra_home, "dashboard_journal.jsonl"))


def _emit(event_type: str, payload: dict, source: str = "dashboard") -> None:
    _event_bus.emit(RuntimeEvent(event_type=event_type, payload=payload, source=source))


# ── Access guard: bearer token + CSRF / DNS-rebinding ───────────────────
# "Local" is not a security boundary: any page open in the same browser can
# reach localhost:8780, and this app indexes arbitrary directories and writes
# into registered ones. A token minted at startup and passed in the URL closes
# that; the SPA keeps it in sessionStorage so navigation inside the app is
# seamless.
#
# Set ASTRA_TOKEN to pin it; otherwise one is generated per process and printed
# to the console. ASTRA_DISABLE_AUTH=1 opts out for a trusted single-user setup.
_ALLOWED_ORIGIN_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
_PUBLIC_PATHS = {"/manifest.webmanifest", "/favicon.ico"}


def _resolve_token() -> tuple[str, bool]:
    if os.environ.get("ASTRA_DISABLE_AUTH") == "1":
        return "", False
    pinned = os.environ.get("ASTRA_TOKEN", "").strip()
    if pinned:
        return pinned, True
    return secrets.token_urlsafe(24), True


_ACCESS_TOKEN, _AUTH_REQUIRED = _resolve_token()


def _bearer_of(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.query_params.get("token", "")


@app.middleware("http")
async def _guard_requests(request: Request, call_next):
    from fastapi.responses import JSONResponse

    path = request.url.path
    needs_token = _AUTH_REQUIRED and path not in _PUBLIC_PATHS and not path.startswith("/static/")
    if needs_token and not secrets.compare_digest(_bearer_of(request), _ACCESS_TOKEN):
        # The first navigation cannot carry a header, so the shell is returned
        # with the token in the body, which the SPA reads on load.
        body = {"detail": "token required", "token": _ACCESS_TOKEN} if path == "/" else {"detail": "invalid or missing token"}
        return JSONResponse(status_code=401, content=body)

    origin = request.headers.get("origin")
    if origin:
        host = origin.split("//", 1)[-1].split("/", 1)[0]
        hostname = host.rsplit(":", 1)[0] if ":" in host else host
        if hostname.lower() not in _ALLOWED_ORIGIN_HOSTS:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=403,
                content={"detail": "cross-origin request refused"},
            )
    return await call_next(request)


def _registered_roots() -> list[str]:
    return [r.root_path for r in _orchestrator.list_repos()]


def _confine_to_registered_repo(candidate: str) -> str:
    """Resolve candidate path and refuse anything outside registered repos.

    All file-read/write endpoints must go through this. Prevents arbitrary
    filesystem read/write from the dashboard. Uses resolve() so symlinks
    pointing outside a registered repo are rejected, not just `..` paths.
    """
    resolved = str(Path(candidate).resolve())
    for root in _registered_roots():
        try:
            Path(resolved).relative_to(str(Path(root).resolve()))
            return resolved
        except ValueError:
            continue
    raise HTTPException(
        status_code=403,
        detail=f"path is outside registered repositories: {os.path.basename(resolved)}",
    )


def _get_or_create(path: str):
    """Look up an already-registered repo. Never registers a new one.

    Registration is an explicit POST (/api/repos/add). Auto-registering here meant
    every read endpoint could pull an arbitrary directory into the graph — and,
    because /api/patch/apply is confined to *registered* roots, hand the caller
    write access to it too.
    """
    root = str(Path(path).resolve())
    rec = _orchestrator.get_repo(root)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"repository not registered: {os.path.basename(root)}")
    if rec.status.value == "registered":
        rec = _orchestrator.index_repo(root)
    return rec


# ── Endpoints ──────────────────────────────────────────────────────────
@app.get("/api/status")
def status():
    repos = _orchestrator.list_repos()
    return {
        "status": "healthy",
        "repos": len(repos),
        "nodes": sum(r.node_count for r in repos),
        "edges": sum(r.edge_count for r in repos),
        "runtime": "active",
        "memory_mb": _health.system_metrics().get("memory_rss_mb", 0),
        "repos_detail": [
            {
                "name": r.name,
                "path": r.root_path,
                "status": r.status.value,
                "nodes": r.node_count,
                "edges": r.edge_count,
                "files": r.file_count,
                "backend": r.storage_backend,
                "last_indexed": r.last_indexed,
                "error": r.error,
                "warnings": list(r.warnings)[:20],
            }
            for r in repos
        ],
        "metrics": {
            "counters": _metrics.counters(),
            "snapshots": [
                {"name": s.name, "value": s.value, "tags": s.tags, "timestamp": s.timestamp}
                for s in _metrics.export_snapshots()[-50:]
            ],
        },
        "events": [
            {"event_type": e.event_type, "payload": e.payload, "source": e.source,
             "span_id": e.span_id, "tags": e.tags, "timestamp": e.timestamp.isoformat()}
            for e in _event_bus.log()[-20:]
        ],
    }


@app.get("/api/repos")
def list_repos():
    return [
        {"name": r.name, "path": r.root_path, "status": r.status.value,
         "nodes": r.node_count, "edges": r.edge_count, "files": r.file_count}
        for r in _orchestrator.list_repos()
    ]


@app.post("/api/repos/add")
async def add_repo(payload: dict):
    path = (payload or {}).get("path", "") if isinstance(payload, dict) else str(payload or "")
    if not path:
        return {"status": "error", "message": "path is required"}
    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail=f"path is not an existing directory: {path}")
    rec = _orchestrator.register_repo(path, backend="duckdb")
    _metrics.increment("repos.added", tags={"name": rec.name})
    _emit("repo_registered", {"name": rec.name})

    _emit("scan_started", {"repo": rec.name, "path": rec.root_path})
    # Indexing is CPU/IO bound and can take minutes on a large repo. Running it
    # inline blocked the whole event loop, stalling every other endpoint and the
    # SSE stream for the duration.
    rec = await run_in_threadpool(_orchestrator.index_repo, rec.root_path)
    if rec.status.value == "failed":
        raise HTTPException(status_code=500, detail=f"indexing failed: {rec.error}")
    _emit("graph_updated", {"repo": rec.name, "nodes": rec.node_count, "edges": rec.edge_count})
    return {
        "name": rec.name,
        "path": rec.root_path,
        "status": rec.status.value,
        "nodes": rec.node_count,
        "edges": rec.edge_count,
        "files": rec.file_count,
        "last_indexed": rec.last_indexed,
        "warnings": list(rec.warnings)[:20],
    }


@app.get("/api/graph/sample")
def graph_sample(path: str, limit: int = 50):
    rec = _get_or_create(path)
    from astra.storage.backend import StorageProvider
    storage = StorageProvider(backend=rec.storage_backend, db_path=rec.db_path).create()
    storage.connect()
    try:
        nodes = storage.get_all_nodes()[:limit]
        edges = storage.get_all_edges()[:min(limit * 3, 150)]
        return {
            "repo": rec.name,
            "nodes": [
                {"id": n.id, "name": n.name,
                 "type": n.type.value if hasattr(n.type, "value") else str(n.type)}
                for n in nodes
            ],
            "edges": [
                {"source": e.from_node, "target": e.to_node,
                 "type": e.type.value if hasattr(e.type, "value") else str(e.type)}
                for e in edges
            ],
        }
    finally:
        storage.close()


@app.get("/api/context")
def context_pack(path: str, query: str, max_tokens: int = 8000):
    root = str(Path(path).resolve())
    _get_or_create(root)
    pack = _orchestrator.query_context(root, seed_node_ids=[], query_intent=query, max_tokens=max_tokens)
    _metrics.increment("context.queries", tags={"repo": root})
    _emit("context_built", {"repo": root, "query": query, "nodes": len(pack.nodes)})
    return {
        "query_intent": pack.query_intent,
        "task_summary": pack.task_summary,
        "node_count": len(pack.nodes),
        "edge_count": len(pack.edges),
        "estimated_tokens": min(pack.total_tokens, pack.token_budget) if pack.token_budget else pack.total_tokens,
        "total_tokens": pack.total_tokens,
        "token_budget": pack.token_budget,
        "confidence": pack.confidence,
        "score": pack.confidence,
        "required_files": list(pack.required_files)[:30],
        "dependency_summary": list(pack.dependency_summary)[:20],
        "hidden_risks": list(pack.hidden_risks)[:10],
        "nodes": [
            {"id": n.node_id if hasattr(n, "node_id") else getattr(n, "id", ""),
             "name": getattr(n, "name", ""),
             "type": n.node_type.name if hasattr(getattr(n, "node_type", None), "name") else "File",
             "file_path": getattr(n, "file_path", ""),
             "relevance": getattr(n, "relevance_score", 1.0)}
            for n in pack.nodes[:30]
        ],
    }


@app.get("/api/execution")
def execution_status(path: str):
    rec = _get_or_create(path)
    return {"repo": rec.name, "status": rec.status.value, "last_indexed": rec.last_indexed,
            "files": rec.file_count, "nodes": rec.node_count, "edges": rec.edge_count}


@app.get("/api/graph/node")
def graph_node(path: str, node_id: str):
    """Node detail with dependency/dependent names for the Execution Engine panel."""
    rec = _get_or_create(path)
    from astra.storage.backend import StorageProvider
    storage = StorageProvider(backend=rec.storage_backend, db_path=rec.db_path).create()
    storage.connect()
    try:
        node = storage.get_node(node_id)
        if node is None:
            return {"error": "node not found", "id": node_id}
        deps = [e.to_node for e in storage.get_edges(from_node=node_id)]
        dependents = [e.from_node for e in storage.get_edges(to_node=node_id)]

        def _name(nid: str) -> str:
            n = storage.get_node(nid)
            # Normalise the separator first, then take the last segment. The
            # previous version split on "\\" then "/" in sequence, so on Linux —
            # where the first split matches nothing — a POSIX path came back
            # whole and the UI rendered "/tmp/pytest-.../lib2.py" as a name.
            if n:
                return n.name
            return nid.replace("\\", "/").rsplit("/", 1)[-1]

        return {
            "id": node.id,
            "name": node.name,
            "type": node.type.name if hasattr(node.type, "name") else str(node.type),
            "metadata": node.metadata,
            "dependencies": [{"id": d, "name": _name(d)} for d in deps[:15]],
            "dependents": [{"id": d, "name": _name(d)} for d in dependents[:15]],
            "dependency_count": len(deps),
            "dependent_count": len(dependents),
        }
    finally:
        storage.close()


@app.get("/api/graph/impact")
def graph_impact(path: str, node_id: str, depth: int = 3):
    """Blast radius of a change: what a node's edit reaches, via BFS over the graph.

    Backed by GraphQueryEngine.impact_analysis, which was written, tested and
    never reachable from the app.
    """
    rec = _get_or_create(path)
    from astra.graph.query_engine import GraphQueryEngine
    from astra.storage.backend import StorageProvider
    storage = StorageProvider(backend=rec.storage_backend, db_path=rec.db_path).create()
    storage.connect()
    try:
        result = GraphQueryEngine(storage).impact_analysis(node_id, depth=depth)
        return {
            "node_id": node_id,
            "depth": depth,
            "affected": [{"id": n.id, "name": n.name, "type": n.type.name} for n in result.nodes[:60]],
            "affected_count": len(result.nodes),
            "edges": [{"from": e.from_node, "to": e.to_node, "type": e.type.name} for e in result.edges[:80]],
        }
    finally:
        storage.close()


@app.get("/api/graph/path")
def graph_path(path: str, from_id: str, to_id: str):
    """Shortest import path between two nodes, or null when unreachable."""
    rec = _get_or_create(path)
    from astra.graph.query_engine import GraphQueryEngine
    from astra.storage.backend import StorageProvider
    storage = StorageProvider(backend=rec.storage_backend, db_path=rec.db_path).create()
    storage.connect()
    try:
        route = GraphQueryEngine(storage).shortest_path(from_id, to_id)
        return {"from": from_id, "to": to_id, "path": route, "length": len(route) - 1 if route else None}
    finally:
        storage.close()


@app.get("/api/logs")
def recent_logs(limit: int = 30):
    return [
        {"timestamp": e.timestamp.isoformat(),
         "event": e.event_type, "data": e.payload}
        for e in _event_bus.log()[-limit:]
    ]


@app.get("/api/health")
def health_check():
    return {"status": _health.overall_status(), "checks": _health.export_health(), "system": _health.system_metrics()}


@app.get("/api/metrics/snapshot")
def metrics_snapshot():
    return _metrics.export_snapshots()


@app.get("/api/explorer")
def explore_repo(path: str):
    """Filesystem-backed tree for a repo."""
    import os
    root = str(Path(path).resolve())
    budget = [_EXPLORER_MAX_ENTRIES]

    def _build(p, depth):
        if budget[0] <= 0:
            return {"name": os.path.basename(p), "path": p, "children": None}
        if not os.path.isdir(p) or depth > _EXPLORER_MAX_DEPTH:
            return {"name": os.path.basename(p), "path": p, "children": None}
        try:
            entries = sorted(os.listdir(p))
        except OSError:
            return {"name": os.path.basename(p), "path": p, "children": None}
        children = []
        for e in entries:
            if e.startswith(".") or e.startswith("__pycache__") or e == "node_modules":
                continue
            if budget[0] <= 0:
                break
            budget[0] -= 1
            fp = os.path.join(p, e)
            if os.path.islink(fp):
                continue
            children.append(_build(fp, depth + 1))
        return {"name": os.path.basename(p), "path": p, "children": children}
    root = _confine_to_registered_repo(root)
    return {"tree": _build(root, 0)}


@app.post("/api/repos/remove")
async def remove_repo(payload: Optional[dict] = None, path: str = ""):
    p = (payload or {}).get("path", "") if isinstance(payload, dict) else ""
    if not p:
        p = path
    _orchestrator.remove_repo(str(Path(p).resolve()))
    _metrics.increment("repos.removed", tags={"path": p})
    return {"status": "removed"}


@app.get("/api/patch/diff")
def patch_diff(path: str, file_path: str = ""):
    """Show file content as a diff-ready block (read confined to registered repos)."""
    import os
    root = str(Path(path).resolve())
    if file_path and os.path.isfile(file_path):
        fp = file_path
    elif file_path:
        fp = os.path.join(root, file_path)
    else:
        return {"file": "", "lines": [], "message": "No file selected"}
    try:
        fp = _confine_to_registered_repo(fp)
    except HTTPException as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc.detail)) from None
    if not os.path.isfile(fp):
        return {"file": fp, "lines": [], "error": "not a file"}
    try:
        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        lines = [{"num": i+1, "text": line, "type": "context"} for i, line in enumerate(content.splitlines())]
        return {"file": fp, "lines": lines[:200], "total": len(lines)}
    except OSError as e:
        return {"file": fp, "lines": [], "error": str(e)}


@app.post("/api/patch/apply")
async def patch_apply(payload: Optional[dict] = None):
    """Simple find-and-replace patch (write confined to registered repos)."""
    import os
    payload = payload or {}
    path = payload.get("path", "")
    file_path = payload.get("file_path", "")
    old_text = payload.get("old_text", "")
    new_text = payload.get("new_text", "")
    root = str(Path(path).resolve())
    fp = os.path.join(root, file_path) if file_path and not os.path.isabs(file_path) else file_path
    try:
        fp = _confine_to_registered_repo(fp)
    except HTTPException as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc.detail)) from None
    if not os.path.isfile(fp):
        return {"status": "error", "message": "not an existing file inside a registered repo"}
    try:
        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if old_text not in content:
            return {"status": "error", "message": "old_text not found in file"}
        new_content = content.replace(old_text, new_text, 1)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(new_content)
        _metrics.increment("patch.applied", tags={"repo": root})
        _emit("patch_applied", {"file": fp, "repo": root})
        _journal.log_event("patch_apply", {
            "file": fp,
            "repo": root,
            "old_text": old_text,
            "new_text": new_text,
        })
        return {"status": "applied", "file": fp}
    except OSError as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/patch/analyze")
async def patch_analyze(payload: Optional[dict] = None):
    """Analyze patch impact: AST diff, dependency impact, risk score, confidence."""
    import os
    payload = payload or {}
    path = payload.get("path", "")
    file_path = payload.get("file_path", "")
    old_text = payload.get("old_text", "")
    new_text = payload.get("new_text", "")
    root = str(Path(path).resolve())
    fp = os.path.join(root, file_path) if file_path and not os.path.isabs(file_path) else file_path
    # Confine first, outside the try: this is the security check, and wrapping
    # it meant a failure inside it came back as an ordinary {"status": "error"}
    # that looked identical to a bad request.
    fp = _confine_to_registered_repo(fp)
    try:
        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        # Parse AST for semantic analysis
        from astra.patch.analyzer import diff_ast, score_risk

        new_content = content.replace(old_text, new_text, 1) if old_text else content
        try:
            # Parsed once here. It was parsed again further down to compute the
            # risk score, so the first result was thrown away and every analyze
            # cost two parses of both revisions.
            ast_diff = diff_ast(content, new_content)
        except SyntaxError:
            return {"status": "error", "message": "Invalid Python syntax in patch"}
        added, removed, modified = ast_diff.added, ast_diff.removed, ast_diff.modified

        # Load graph for dependency impact
        from astra.storage.backend import StorageProvider
        rec = _orchestrator.get_repo(root) if hasattr(_orchestrator, 'get_repo') else None
        dep_impact: dict = {"upstream": 0, "downstream": 0, "affected_files": []}
        if rec:
            storage = StorageProvider(backend=rec.storage_backend, db_path=rec.db_path).create()
            storage.connect()
            try:
                all_nodes = storage.get_all_nodes()
                all_edges = storage.get_all_edges()
                # Find nodes in this file
                file_nodes = [n for n in all_nodes if n.metadata.get('file_path') == fp]
                for fn in file_nodes:
                    # Count downstream (dependents)
                    dependents = [e for e in all_edges if e.from_node == fn.id]
                    dep_impact["downstream"] += len(dependents)
                    # Count upstream (dependencies)
                    dependencies = [e for e in all_edges if e.to_node == fn.id]
                    dep_impact["upstream"] += len(dependencies)
            finally:
                storage.close()

        # Risk scoring
        report = score_risk(ast_diff, downstream=dep_impact["downstream"])

        # Semantic diff output
        diff_lines = []
        if old_text and new_text:
            diff_lines.append({"type": "del", "text": old_text[:200]})
            diff_lines.append({"type": "add", "text": new_text[:200]})

        return {
            "status": "analyzed",
            "file": fp,
            "ast_diff": {
                "added_symbols": list(added),
                "removed_symbols": list(removed),
                "modified_symbols": list(modified),
            },
            "dependency_impact": dep_impact,
            "risk_score": report.score,
            "confidence": report.confidence,
            "risk_level": report.level,
            "diff_preview": diff_lines,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/timeline")
def cognitive_timeline(limit: int = 20):
    """Cognitive Timeline — chronological event trace."""
    events = _event_bus.log()[-limit:]
    return [
        {
            "timestamp": e.timestamp.isoformat(),
            "event": e.event_type,
            "detail": e.payload,
            "source": e.source,
        }
        for e in events
    ]


@app.get("/api/executions/journal")
def journal_recent(limit: int = 50):
    """Recent journaled execution entries."""
    events = _journal.read_events()[-limit:]
    return [
        {
            "timestamp": e.get("timestamp", ""),
            "type": e.get("type", ""),
            "sequence": e.get("sequence", 0),
            "data": e.get("data", {}),
        }
        for e in events
    ]


@app.post("/api/executions/replay")
async def replay_executions(payload: Optional[dict] = None):
    """Replay journaled execution events through ReplayEngine.

    Accepts {"journal_path": "..."} (confined to registered repos or the
    runtime journal itself) and optionally {"from_sequence": N}.
    """
    payload = payload or {}
    journal_path = payload.get("journal_path") or _journal.journal_path
    from_sequence = payload.get("from_sequence")

    try:
        if os.path.abspath(journal_path) != os.path.abspath(_journal.journal_path):
            journal_path = _confine_to_registered_repo(journal_path)
    except HTTPException as exc:
        return {"status": "error", "message": str(exc.detail)}

    engine = ReplayEngine(journal_path)
    engine.load_journal()

    replayed: list[dict] = []

    def _collect(event):
        replayed.append({
            "event_type": event.event_type,
            "payload": event.payload,
            "timestamp": event.timestamp,
            "sequence": event.sequence,
        })

    if from_sequence is not None:
        count = engine.replay_from_sequence(int(from_sequence), _collect)
    else:
        count = engine.replay(_collect)

    return {
        "status": "replayed",
        "journal_path": journal_path,
        "count": count,
        "last_sequence": engine.get_last_sequence(),
        "events": replayed[-100:],
    }


# ── SSE stream for real-time dashboard updates ──────────────────────────
@app.get("/api/stream")
async def event_stream(request: Request):
    """Server-Sent Events stream for live dashboard updates."""
    from sse_starlette.sse import EventSourceResponse

    async def event_generator():
        last_idx = len(_event_bus.log())
        try:
            while True:
                if await request.is_disconnected():
                    break
                events, last_idx = _event_bus.log_since(last_idx)
                if events:
                    for e in events:
                        import json
                        yield {
                            "event": e.event_type,
                            "data": json.dumps({
                                "timestamp": e.timestamp.isoformat(),
                                "type": e.event_type,
                                "detail": e.payload,
                                "source": e.source,
                            })
                        }
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass

    return EventSourceResponse(event_generator())


# ── SPA (read on every request so edits hot-reload) ───────────────────
@app.get("/", response_class=HTMLResponse)
def dashboard():
    from fastapi.responses import HTMLResponse as _HR
    html = (Path(__file__).parent / "dashboard_real.html").read_text(encoding="utf-8")
    return _HR(content=html, headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"})


# ── Brand assets: favicon, PWA icons, manifest ─────────────────────────
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(Path(__file__).parent / "favicon.ico", media_type="image/x-icon")


app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.get("/manifest.webmanifest", include_in_schema=False)
def web_manifest():
    return FileResponse(
        Path(__file__).parent / "manifest.webmanifest",
        media_type="application/manifest+json",
    )


@app.post("/api/agent/propose")
async def agent_propose(payload: Optional[dict] = None):
    """Answer a question by proposing an edit — without writing anything.

    Takes the same `reply` the agent loop would get from a model, so the caller
    runs the model wherever it likes and posts the answer here. The response is
    the review: which edits were parsed, which were rejected and why, the diff
    of each surviving edit, and the risk. Applying stays /api/patch/apply, a
    separate call, so nothing is written by proposing.
    """
    from astra.agent.loop import parse_edits, review

    payload = payload or {}
    root = _confine_to_registered_repo(str(Path(payload.get("path", "")).resolve()))
    reply = payload.get("reply", "")

    edits, warnings = parse_edits(reply)
    if warnings:
        return {"status": "rejected", "warnings": list(warnings), "edits": []}

    def dependents(relative: str) -> int:
        """How many nodes an edit to this file reaches. A bad count must not
        fail the review, so it degrades to zero rather than propagating."""
        try:
            rec = _get_or_create(root)
            from astra.graph.query_engine import GraphQueryEngine
            from astra.storage.backend import StorageProvider

            storage = StorageProvider(
                backend=rec.storage_backend, db_path=rec.db_path
            ).create()
            storage.connect()
            try:
                analysis = GraphQueryEngine(storage).impact_analysis(
                    f"file:{relative}", depth=2
                )
                return max(len(analysis.nodes) - 1, 0)
            finally:
                storage.close()
        except Exception:  # noqa: BLE001 - the count is advisory
            return 0

    result = review(tuple(edits), root, downstream_counts=dependents)

    return {
        "status": "reviewed" if result.applies_cleanly else "rejected",
        "risk": result.risk,
        "confidence": result.confidence,
        "downstream": result.downstream,
        "warnings": list(result.warnings),
        "edits": [
            {
                "path": edit.path,
                "reason": edit.reason,
                "added": diff.added,
                "removed": diff.removed,
                "modified": diff.modified,
            }
            for edit, (_path, diff) in zip(result.edits, result.diffs, strict=False)
        ],
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8780"))
    if _AUTH_REQUIRED:
        # ASCII only: the Windows console defaults to cp1252 and would crash on
        # a box-drawing arrow or any other non-Latin glyph.
        print("\n  SL-AstraCore Observatory")
        print(f"  Open  http://127.0.0.1:{port}/?token={_ACCESS_TOKEN}\n")
        print("  (set ASTRA_TOKEN to pin it, or ASTRA_DISABLE_AUTH=1 to opt out)\n")
    uvicorn.run(app, host="0.0.0.0", port=port)
