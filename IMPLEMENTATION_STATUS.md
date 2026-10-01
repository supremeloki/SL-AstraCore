# SL-AstraCore implementation status

Measured 2026-10-01. Every number below was re-measured against this tree;
nothing is carried over from an earlier audit.

## What it is

A local tool that reads one repository, turns it into a graph in DuckDB, and
answers a plain-language question by returning a ranked bundle of real source.
A FastAPI dashboard shows the graph and the answer; `astra` does the same from
a terminal.

```
RepositoryScanner -> ParserRegistry -> import_resolver -> DuckDB -> context stack -> dashboard / CLI
```

94 modules, 9,041 lines under `astra/`, plus `dashboard_app.py`.

## Measured

| | |
|---|---|
| index this repository (165 files) | 2.3s (72 files/s) |
| index 3,000 files | 10.1s (296 files/s) |
| query | 111ms median |
| ranking accuracy, 12 real questions | 11/12 first place, 12/12 top three |
| pack carrying source, 4k budget | 7 of 13 nodes |
| source per 8x budget | 8.0x |

| Gate | |
|---|---|
| `pytest tests/ -q` | 281 passed, 1 skipped |
| `ruff check astra/ tests/ dashboard_app.py` | clean |
| `mypy astra/ dashboard_app.py` | clean, 95 files |
| Linux + Windows, Python 3.11 and 3.12 | green |

## Deliberate limitations

- **No agent layer.** Nothing calls an LLM, applies a patch, or validates a
  result. The dashboard can compute a semantic diff and a risk score for a
  proposed edit; closing the loop is the caller's job.
- **A re-index re-reads every file.** Edges come from pairs of files, so
  skipping unchanged ones leaves stale edges pointing at them. Tried; it was
  silently wrong; reverted.
- **Single-user access control.** A per-process token, not accounts. It binds
  all interfaces, so do not expose it beyond a trusted network. Set
  `ASTRA_TOKEN` to pin the token; there is no TLS.
- **Config files are not parsed.** `.json` / `.yaml` / `.toml` are indexed as
  files with no structural detail.
- **Naming conflicts are file-level.** Two modules may define the same class
  without a conflict being reported; only the same file base name in different
  modules counts.
- **Tree-sitter needs a cache directory.** With neither `HOME` nor
  `XDG_CACHE_HOME`, grammars cannot be downloaded and non-Python parsing is
  skipped rather than failing.
- **BLIND_MAX depth.** Source nested past ~900 levels is skipped.

## Removed

46 modules and ~2,800 lines with no caller outside their own tests were
deleted: the agent provider layer, the resilience stack (retry, circuit
breaker, sandbox, quotas), and two code paths no engine reached.

They are gone from history as well as the tree — there is no branch holding
them. Kept: `astra/cli` (the console script), `astra/patch/analyzer`
(reachable from `dashboard_app.py`), `astra/core/config.py`.

If one of them is wanted again it has to be rewritten; nothing to restore from.