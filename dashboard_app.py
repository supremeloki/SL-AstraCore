"""SL-AstraCore Dashboard — Real API backed by Core + Runtime."""

from pathlib import Path
import asyncio

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from astra.runtime.orchestrator import RuntimeOrchestrator
from astra.runtime.metrics import MetricsCollector
from astra.runtime.event_bus import EventBus, RuntimeEvent
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
        _event_bus.emit(RuntimeEvent(event_type="repo_registered", payload={"name": rec.name}))
    if rec.status.value not in ("active", "indexing"):
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
            }
            for r in repos
        ],
        "metrics": _metrics.export_snapshots(),
        "events": [
            {"event_type": e.event_type, "payload": e.payload, "source": e.source, "span_id": e.span_id, "tags": e.tags}
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
    rec = _orchestrator.register_repo(path, backend="duckdb")
    _event_bus.emit(RuntimeEvent(event_type="repo_registered", payload={"name": rec.name}))
    rec = _orchestrator.index_repo(rec.root_path)
    return {
        "name": rec.name,
        "path": rec.root_path,
        "status": rec.status.value,
        "nodes": rec.node_count,
        "edges": rec.edge_count,
        "files": rec.file_count,
        "last_indexed": rec.last_indexed,
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
        {"timestamp": e.timestamp.isoformat() if hasattr(e, "timestamp") else "",
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
    def _build(p):
        if not os.path.isdir(p):
            return {"name": os.path.basename(p), "path": p, "children": None}
        entries = sorted(os.listdir(p))
        children = []
        for e in entries:
            if e.startswith(".") or e.startswith("__pycache__") or e == "node_modules":
                continue
            fp = os.path.join(p, e)
            children.append(_build(fp))
        return {"name": os.path.basename(p), "path": p, "children": children}
    return {"tree": _build(root)}


@app.post("/api/repos/remove")
async def remove_repo(payload: dict = None, path: str = ""):
    p = (payload or {}).get("path", "") if isinstance(payload, dict) else ""
    if not p:
        p = path
    _orchestrator.remove_repo(str(Path(p).resolve()))
    return {"status": "removed"}


@app.get("/api/patch/diff")
def patch_diff(path: str, file_path: str = ""):
    """Show file content as a diff-ready block."""
    import os
    root = str(Path(path).resolve())
    if file_path and os.path.isfile(file_path):
        fp = file_path
    elif file_path:
        fp = os.path.join(root, file_path)
    else:
        return {"file": "", "lines": [], "message": "No file selected"}
    try:
        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        lines = [{"num": i+1, "text": l, "type": "context"} for i, l in enumerate(content.splitlines())]
        return {"file": fp, "lines": lines[:200], "total": len(lines)}
    except Exception as e:
        return {"file": fp, "lines": [], "error": str(e)}


@app.post("/api/patch/apply")
async def patch_apply(payload: dict = None):
    """Simple find-and-replace patch."""
    import os
    payload = payload or {}
    path = payload.get("path", "")
    file_path = payload.get("file_path", "")
    old_text = payload.get("old_text", "")
    new_text = payload.get("new_text", "")
    root = str(Path(path).resolve())
    fp = os.path.join(root, file_path) if file_path and not os.path.isabs(file_path) else file_path
    try:
        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if old_text not in content:
            return {"status": "error", "message": "old_text not found in file"}
        new_content = content.replace(old_text, new_text, 1)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(new_content)
        _event_bus.emit(RuntimeEvent(event_type="patch_applied", payload={"file": fp, "repo": root}))
        return {"status": "applied", "file": fp}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/patch/analyze")
async def patch_analyze(payload: dict = None):
    """Analyze patch impact: AST diff, dependency impact, risk score, confidence."""
    import os, ast
    payload = payload or {}
    path = payload.get("path", "")
    file_path = payload.get("file_path", "")
    old_text = payload.get("old_text", "")
    new_text = payload.get("new_text", "")
    root = str(Path(path).resolve())
    fp = os.path.join(root, file_path) if file_path and not os.path.isabs(file_path) else file_path
    try:
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
        dep_impact = {"upstream": 0, "downstream": 0, "affected_files": []}
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
            "timestamp": e.timestamp.isoformat() if hasattr(e, "timestamp") else "",
            "event": e.event_type,
            "detail": e.payload,
            "source": e.source,
        }
        for e in events
    ]


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
                                "timestamp": e.timestamp.isoformat() if hasattr(e, "timestamp") else "",
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
