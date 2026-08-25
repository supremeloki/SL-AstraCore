# SL-AstraCore Implementation Status

Updated: 2026-08-25. Replaces the 2026-07-07 audit, which no longer matched
the tree (it predated the storage backends, parser adapters, FastAPI dashboard
and runtime module stack). Scores below come from `.audit_findings.json`.

## Summary

The pipeline is executable end to end:

`RepositoryScanner -> ParserRegistry -> import_resolver -> DuckDB/SQLite storage -> context stack -> RuntimeOrchestrator -> FastAPI dashboard (SSE)`

Baseline: `python -m pytest tests/ -q` => 265 passed, 1 skipped.

## Audit scores by dimension

| Dimension | Score |
|---|---:|
| End-to-end runtime behavior | 74% |
| Spec completeness vs docs/sas/*.md | 61% |
| Bugs and correctness defects | 55% |
| Architecture and code-quality debt | 55% |
| Performance bottlenecks | 52% |
| Security review of exposed surfaces | 38% |
| Docs, config, packaging, repo hygiene | 42% |

## Phase status

| Phase | Component | State |
|---|---|---|
| 1 | Repository Scanner | Strongest phase: streaming scan, JSONL export, hash checkpoint resume, persistent index storage |
| 2 | Universal Parser | Python strong; JS/TS regex-based with known import-regex gaps; Markdown/config partial; tree-sitter engine exists but unwired; other languages fall back to text blocks |
| 3 | Knowledge Graph | Persistent DuckDB/SQLite backends + mutator diffing work; enrichers (vault/conflict/pattern) built and tested but not wired into the pipeline; shortest_path/subgraph queries protocol-only |
| 4 | Context Engine | Packs generate and rank; token budget not enforced on all paths; snippets/vault_context fields never populated |
| 5 | Runtime Orchestrator | Index/query lifecycle works; ToolRegistry/ValidationEngine/RecoveryEngine protocols have no implementations; plan step states never transition |
| 6 | Dashboard + Control Plane | Full FastAPI app with SSE streaming serves the SPA; replay engine/journal implemented but unreached; several typed events never emitted; metrics collector unfed |
| 7 | Agent Adapter Layer | Skeleton: providers echo/static stubs, output schema declared but unvalidated, no fallback chain |

## Known top issues (from audit)

1. Security: `/api/patch/apply` allows arbitrary file write via absolute/traversal paths; `/api/patch/diff` arbitrary read; `/api/repos/add` indexes any directory. No auth on any endpoint.
2. Correctness: relative imports resolve to wrong files; JS/TS relative imports never resolve; async functions invisible to the parser.
3. Architecture: ~20 of 34 runtime modules are tests-only dead weight in four parallel stacks; three conflicting ExecutionPlan classes; two unrelated ContextEngine classes.
4. Performance: index_repo persists row-by-row (~53x slower than the existing batch API); resolver rebuilds a set per dependency.

## Change log

- 2026-08-25: Packaging/docs repair — requirements.txt now matches real imports (added psutil, sse-starlette; dropped unused toml/python-dotenv/websockets/rich/click), pyproject [project] dependencies/classifiers/[project.scripts] added, stdlib argparse CLI (`astra index|context|serve`) implemented, README created, this file regenerated from `.audit_findings.json`.
