# SL-AstraCore

Repository Cognitive Intelligence Platform: scan a codebase, build a knowledge
graph of files and dependencies, and generate task-specific context packs for
AI coding agents.

Pipeline: `RepositoryScanner -> ParserRegistry -> import_resolver -> DuckDB/SQLite storage -> enrichment -> context stack -> RuntimeOrchestrator -> FastAPI dashboard`.

## Install

Requires Python 3.11+.

```
pip install -r requirements.txt
pip install -e .
```

Or with Docker:

```
docker compose up --build     # dashboard on http://localhost:8780
```

## Usage

Index a repository and query it from the command line:

```
astra index <path>            # scan -> parse -> resolve -> enrich -> persist graph
astra context <path> "<query>"  # print a ranked context pack for the query
astra serve --port 8000       # start the dashboard (http://127.0.0.1:8000)
```

Or run the dashboard directly: `python dashboard_app.py` (port 8780, override with `PORT`).

Repository data (per-repo graph DBs, journal) lives in `~/.astra`; set `ASTRA_HOME`
to relocate it.

### Agent providers

Task execution goes through configurable providers listed in `astra.yaml`:

```yaml
agent:
  providers: [generic, codex, manual]
```

- `generic` — echo fallback (default when no key is set)
- `codex` — runs the real Codex CLI (`codex exec`); skipped if the binary is absent
- `manual` — renders a task brief for human/VS Code execution; pass an optional response callback

## Run tests

```
python -m pytest tests/ -q
```

Quality gates: `python -m mypy astra/ dashboard_app.py` and
`python -m ruff check astra/ dashboard_app.py tests/` are both clean.

## Architecture

- **astra/scanner** — streaming filesystem walk with hash-based checkpoint resume.
- **astra/parser** — per-language adapters behind one registry: Python via `ast`, JS/TS + Go + Rust + Java + C/C++ + C# + Ruby + PHP via tree-sitter, Markdown; graceful fallback for unknown types.
- **astra/resolver** — resolves imports to intra-repo graph edges.
- **astra/storage** — DuckDB (default) and SQLite backends for graph nodes/edges with batch upserts.
- **astra/graph** — mutation diffing plus pattern/conflict enrichment wired into indexing.
- **astra/context** — task analysis, ranking and token budgeting over the graph to produce context packs.
- **astra/runtime** — `RuntimeOrchestrator` tying it together, plus metrics/event-bus/health telemetry stack and resilience modules (retry, checkpoint, circuit breaker, replay journal).
- **dashboard_app.py** — FastAPI control plane serving `dashboard_real.html` with SSE live events.

## Status

| Phase | Component | State |
|---|---|---|
| 1 | Repository Scanner | Working; runtime uses direct walk (streaming checkpoint path reserved for large repos) |
| 2 | Universal Parser | Working: Python AST + tree-sitter for 12 languages + Markdown; config files fall back to text blocks |
| 3 | Knowledge Graph | Working: persistent storage, batch upserts, IMPORTS edges + pattern/conflict enrichment; shortest_path/subgraph in query engine |
| 4 | Context Engine | Working: ranked packs with token budget; snippets not populated |
| 5 | Runtime Orchestrator | Index/context lifecycle works; plan execution/recovery modules unwired |
| 6 | Dashboard + Control Plane | Working FastAPI app with SSE, live star-chart UI; replay endpoints present |
| 7 | Agent Adapter Layer | Config-driven providers; codex CLI bridge real; output schema not yet validated |

Details: [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md), specs in `docs/sas/`.
