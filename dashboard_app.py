"""SL-AstraCore Dashboard — Real API backed by Core + Runtime."""

from pathlib import Path
import asyncio
import os
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
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
from astra.parser.registry import ParserRegistry
from astra.parser.python_adapter import PythonParserAdapter
from astra.parser.jsts_adapter import JSTSParserAdapter
from astra.parser.markdown_adapter import MarkdownParserAdapter

app = FastAPI(title="SL-AstraCore", docs_url="/docs")

# ── Runtime ────────────────────────────────────────────────────────────
_registry = ParserRegistry()
_registry.register(PythonParserAdapter())
_registry.register(JSTSParserAdapter())
_registry.register(MarkdownParserAdapter())
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
    """Register repo if new, index if stale."""
    from pathlib import Path as _P
    root = str(_P(path).resolve())
    try:
        rec = _orchestrator.get_repo(root)
    except Exception:
        rec = None
    if rec is None:
        rec = _orchestrator.register_repo(root, backend="duckdb")
        _metrics.increment("repos.added", tags={"name": rec.name})
        _emit("repo_registered", {"name": rec.name})
    # Re-index only fresh registrations; a failed repo must not trigger a
    # synchronous full re-index on every request (death spiral).
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
    rec = _orchestrator.index_repo(rec.root_path)
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
        "estimated_tokens": min(pack.total_tokens, max_tokens) if max_tokens else pack.total_tokens,
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
            return n.name if n else nid.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]

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
        raise HTTPException(status_code=exc.status_code, detail=str(exc.detail))
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
        raise HTTPException(status_code=exc.status_code, detail=str(exc.detail))
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
    import ast
    payload = payload or {}
    path = payload.get("path", "")
    file_path = payload.get("file_path", "")
    old_text = payload.get("old_text", "")
    new_text = payload.get("new_text", "")
    root = str(Path(path).resolve())
    fp = os.path.join(root, file_path) if file_path and not os.path.isabs(file_path) else file_path
    try:
        fp = _confine_to_registered_repo(fp)
        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        # Parse AST for semantic analysis
        try:
            old_ast = ast.parse(content)
            new_content = content.replace(old_text, new_text, 1) if old_text else content
            new_ast = ast.parse(new_content)
        except SyntaxError:
            return {"status": "error", "message": "Invalid Python syntax in patch"}

        # Compute AST diff
        old_nodes = {n for n in ast.walk(old_ast) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        new_nodes = {n for n in ast.walk(new_ast) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}

        old_names = {n.name for n in old_nodes}
        new_names = {n.name for n in new_nodes}

        added = new_names - old_names
        removed = old_names - new_names
        modified = old_names & new_names

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
        risk = 0
        risk += len(removed) * 10  # Breaking changes
        risk += len(modified) * 3  # Modifications
        risk += dep_impact["downstream"] * 2  # Downstream impact
        risk += len(added) * 1  # New symbols (lower risk)

        # Confidence: high if small change, low if many dependencies
        confidence = max(0.1, 1.0 - (risk / 100))

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
            "risk_score": min(100, risk),
            "confidence": round(confidence, 2),
            "risk_level": "high" if risk > 50 else "medium" if risk > 20 else "low",
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
                events = _event_bus.log()
                if len(events) > last_idx:
                    for e in events[last_idx:]:
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
                    last_idx = len(events)
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8780")))
