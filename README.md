# SL-AstraCore

Repository Cognitive Intelligence Platform: scan a codebase, build a knowledge
graph of files and dependencies, and generate task-specific context packs for
AI coding agents.

Pipeline: `RepositoryScanner -> ParserRegistry -> import_resolver -> DuckDB/SQLite storage -> context stack -> RuntimeOrchestrator -> FastAPI dashboard`.

## Install

Requires Python 3.11+.

```
pip install -r requirements.txt
pip install -e .
```

## Usage

Index a repository and query it from the command line:

```
astra index <path>            # scan -> parse -> resolve -> persist graph
astra context <path> "<query>"  # print a ranked context pack for the query
astra serve --port 8000       # start the dashboard (http://127.0.0.1:8000)
```


## Run tests

```
python -m pytest tests/ -q
```

## Architecture

- **astra/scanner** — streaming filesystem walk with hash-based checkpoint resume.
- **astra/parser** — per-language adapters (Python via `ast`, JS/TS, Markdown) behind one registry; graceful text fallback for unknown types.
- **astra/resolver** — resolves imports to intra-repo graph edges.
- **astra/storage** — DuckDB (default) and SQLite backends for graph nodes/edges with batch upserts.
- **astra/graph** — in-memory graph store, mutation diffing, conflict/vault enrichers.
- **astra/context** — task analysis, ranking and token budgeting over the graph to produce context packs.
- **astra/runtime** — `RuntimeOrchestrator` tying it together, plus metrics/event-bus/health telemetry stack and resilience modules (retry, checkpoint, circuit breaker, replay journal).
- **dashboard_app.py** — FastAPI control plane serving `astra/dashboard/dashboard_real.html` with SSE live events.

## Status

| Phase | Component | State |
|---|---|---|
| 1 | Repository Scanner | Working: streaming scan, checkpoint resume, persistent index |
| 2 | Universal Parser | Partial: Python strong, JS/TS regex-based, Markdown; other languages fall back to text blocks; tree-sitter engine present but unwired |
| 3 | Knowledge Graph | Mostly working: persistent storage + upserts; some enrichers not yet wired into the pipeline; path/subgraph queries missing |
| 4 | Context Engine | Functional but budget enforcement is incomplete; snippets not populated |
| 5 | Runtime Orchestrator | Index/context lifecycle works; plan execution/recovery modules exist but are unwired |
| 6 | Dashboard + Control Plane | Working FastAPI app with SSE; replay endpoints and typed lifecycle events missing |
| 7 | Agent Adapter Layer | Skeleton only: providers are stubs, no real agent execution |

Details: [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md), specs in `docs/sas/`.
