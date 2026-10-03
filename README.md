<div align="center">

<img src="docs/logo.png" width="128" alt="SL-AstraCore logo"/>

# SL-AstraCore

**Repository Observatory — turn any codebase into a navigable knowledge graph**

Scan → Parse → Graph → Enrich → Context Packs, behind a live star-chart dashboard.

[![Tests](https://img.shields.io/badge/tests-281%20passed-brightgreen)](#quality)
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
- **Agent loop** — packs the repository, reviews a model's proposed edit against the real files, and refuses anything unanchored, unparsable or unparsed; applying is a separate, explicit step
- **Live dashboard** — SSE event stream, interactive canvas star chart, file explorer, patch review, execution monitor, telemetry sparklines

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
# 1. launch the observatory — it prints a URL containing a one-time token
python dashboard_app.py
#   Open  http://127.0.0.1:8780/?token=...

# 2. add a repository from the UI, or use the CLI:
astra index F:\path\to\repo
astra context F:\path\to\repo "how does authentication work"
astra serve --port 8780
```

### Ask a question and get a reviewed edit

The agent loop takes the answer from whatever model you use, reviews it against
the real files, and writes nothing until you say so:

```bash
# run your model however you like, then review its reply
astra propose F:\path\to\repo "why does charge subtract one" \
    --reply reply.json --emit proposal.json

# read it, then apply it
astra apply F:\path\to\repo proposal.json
```

The same review is `POST /api/agent/propose`, which takes the model's reply and
returns the diff, the risk, and why anything was rejected. An edit whose
`old_text` is not verbatim in the file it names is refused rather than applied,
and `astra apply` refuses a proposal whose file changed since the review.

The dashboard mints an access token at startup and requires it on every API
call, so a page open in the same browser cannot drive it. Pin the token with
`ASTRA_TOKEN=...`, or set `ASTRA_DISABLE_AUTH=1` on a trusted single-user
machine to opt out.

Repository data lives in `~/.astra` (override with the `ASTRA_HOME` environment
variable). Each repo gets its own deterministic graph database.

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
                       ContextEngine ← RuntimeOrchestrator
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
| `astra/runtime` | orchestrator, event bus, replayable execution journal |
| `astra/patch` | semantic diff and risk scoring for a proposed edit |
| `astra/agent` | the loop: pack → model → reviewed edit → explicit apply |

## Quality

```bash
python -m pytest tests/ -q                      # 418 passed, 1 skipped
python -m mypy astra/ dashboard_app.py          # Success: no issues in 96 files
python -m ruff check astra/ tests/ dashboard_app.py   # All checks passed
```

The codebase is type-clean under mypy (0 errors over 96 files) and lint-clean
under a project-owned ruff ruleset, with CI running both on Python 3.11 and 3.12
across Linux and Windows. Measured on this repository:

| | |
|---|---|
| index 3,000 files | 7.5s (402 files/s) |
| query | 62ms median |
| ranking accuracy, 12 real questions | 8/12 first place, 12/12 top three |
| pack carrying source at a 4k budget | 8 of 13 nodes |

### Known limitations

Deliberate, not accidental:

- **Single-user access control.** The dashboard is protected by a per-process
  token, not by accounts or roles: anyone who can read the URL can use it, and
  the server binds all interfaces so it is reachable from other machines on the
  network. Set `ASTRA_TOKEN` to pin the token; there is no TLS, so do not expose
  it beyond a trusted network.
- **No provider is wired in.** The agent loop takes the model's reply and
  reviews it; it never calls one. Running a model is the caller's, because a
  bundled provider means an API key, a network dependency and a bill.
- **A re-index reads the whole node table.** Unchanged files are not parsed
  again, which makes a re-index with nothing to do about 3x faster than a full
  one, but the write still reads every node, so a run with one changed file
  costs about the same as a full index.
- **Config keys are indexed, values are not.** `.json` / `.yaml` / `.toml` are
  parsed for their key paths (`server.port`), so a question about a setting
  finds the file that declares it. The values themselves are not in the graph.
- **BLIND_MAX depth.** Source nested deeper than ~900 levels (minified
  JavaScript) is skipped by the tree-sitter traversal.

## License

MIT — see [LICENSE](LICENSE).
