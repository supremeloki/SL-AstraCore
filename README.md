<div align="center">

<img src="docs/logo.png" width="128" alt="SL-AstraCore logo"/>

# SL-AstraCore

**Repository Observatory — turn any codebase into a navigable knowledge graph**

Scan → Parse → Graph → Enrich → Context Packs, behind a live star-chart dashboard.

[![Tests](https://img.shields.io/badge/tests-330%20passed-brightgreen)](#quality)
[![mypy](https://img.shields.io/badge/mypy-clean-blue)](#quality)
[![ruff](https://img.shields.io/badge/ruff-clean-blue)](#quality)
[![Python](https://img.shields.io/badge/python-3.11+-informational)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-windows%20%7C%20linux%20%7C%20macOS-lightgrey)](#install)

</div>

---

**SL-AstraCore** indexes a repository into a persistent knowledge graph — files,
functions, classes and their import relationships — then answers natural-language
queries with ranked, token-budgeted context packs ready to hand to any AI coding
agent.

The dashboard renders your repository as a **star chart**: every file is a star,
every import a constellation line, patterns and conflicts are marked in the log.

## Features

- **11 parser adapters over 22 file extensions** — Python via `ast`; JavaScript, TypeScript, TSX, Go, Rust, Java, C, C++, C#, Ruby and PHP via tree-sitter; Markdown with wiki-link semantics
- **Persistent knowledge graph** — DuckDB (default) or SQLite, incremental indexing with atomic batch upserts
- **Graph enrichment** — design-pattern detection (`repository`, `factory`, …), naming-convention analysis and cross-module naming-conflict detection, all wired into the index pipeline
- **Context engine** — intent analysis, keyword/seed ranking, BFS dependency expansion, hard token budgets
- **Agent adapter layer** — config-driven providers: `generic` fallback, real **Codex CLI** bridge, `manual` hand-off briefs for human/VS Code execution
- **Live dashboard** — SSE event stream, interactive canvas star chart, file explorer, patch review, execution monitor, telemetry sparklines
- **Resilience stack** — retry with jitter, circuit breaker, sandboxing, resource quotas, replayable execution journal

## Install

Requires Python 3.11+.

```bash
git clone https://github.com/supremeloki/SL-AstraCore.git
cd SL-AstraCore
pip install -r requirements.txt
pip install -e .
```

Or run everything in Docker:

```bash
docker compose up --build     # dashboard on http://localhost:8780
```

## Quick start

```bash
# 1. launch the observatory
python dashboard_app.py       # → http://localhost:8780

# 2. add a repository from the UI ("Add repository"), or use the CLI:
astra index F:\path\to\repo
astra context F:\path\to\repo "how does authentication work"
astra serve --port 8780
```

Repository data lives in `~/.astra` (override with the `ASTRA_HOME` environment
variable). Each repo gets its own deterministic graph database.

### Agent providers

Configure task-execution providers in `astra.yaml`:

```yaml
agent:
  providers:
    - generic   # echo fallback (default)
    - codex     # real Codex CLI; skipped when the binary is absent
    - manual    # render a task brief for human / VS Code execution
```

## Dashboard

| Panel | What it shows |
|---|---|
| **Explorer** | full filesystem tree of the registered repo |
| **Star Chart** | knowledge graph as an interactive star map — degree-sized stars, selection reticle, zoom/pan |
| **Inspector** | spectral breakdown of the selected node: dependencies, dependents |
| **Context** | live context packs: tokens, nodes, confidence + top-ranked files |
| **Monitor** | pipeline progress from the SSE stream |
| **Patch Review** | per-file review with apply/reject actions |
| **Runtime / Telemetry / Signal Log** | store health, memory gauge, latency sparks, live event feed |

## Architecture

```text
RepositoryScanner → ParserRegistry → ImportResolver → DuckDB/SQLite
                                                    ↓
                                        Pattern/Conflict Enrichment
                                                    ↓
                       ContextEngine ← RuntimeOrchestrator ← Agent Providers
                              ↓
                     FastAPI Dashboard (SSE)
```

| Module | Responsibility |
|---|---|
| `astra/scanner` | streaming walk, hash checkpoint resume, ignore rules |
| `astra/parser` | per-language adapters behind one registry; graceful text fallback |
| `astra/resolver` | imports → intra-repo graph edges |
| `astra/graph` | mutator diffing, pattern/conflict enrichment |
| `astra/storage` | DuckDB/SQLite backends, set-based upserts |
| `astra/context` | task analysis, ranking, token budgeting |
| `astra/runtime` | orchestrator, metrics/events/journal, resilience modules |
| `astra/agents` | provider registry: generic / codex / manual |

## Quality

```bash
python -m pytest tests/ -q                      # 370 passed, 1 skipped
python -m mypy astra/ dashboard_app.py          # Success: no issues in 150 files
python -m ruff check astra/ tests/              # All checks passed
```

The codebase is type-clean under mypy (0 errors) and lint-clean under a
project-owned ruff ruleset, with CI running both on Python 3.11 and 3.12 across
Linux and Windows. It was audited across eight dimensions (runtime behaviour,
spec completeness, correctness, architecture, performance, security, packaging,
hygiene); the findings that mattered were fixed, and the rest are noted below.

### Known limitations

Deliberate, not accidental:

- **Single-user, no authentication.** The dashboard is a local tool; it refuses
  cross-origin requests but assumes a trusted host.
- **Phase 5/7 are opt-in.** `ToolRegistry` / `ValidationEngine` /
  `RecoveryEngine` are declared protocols with no implementation, and the
  agent providers are reachable from the library and CLI rather than wired into
  the dashboard. Use them directly or wire them up.
- **Config files are not parsed.** `.json` / `.yaml` / `.toml` are indexed as
  files with no structural detail.
- **BLIND_MAX depth.** Source nested deeper than ~900 levels (minified
  JavaScript) is skipped by the tree-sitter traversal.

## License

MIT — see [LICENSE](LICENSE).
