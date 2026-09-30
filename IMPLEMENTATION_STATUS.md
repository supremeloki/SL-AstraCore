# SL-AstraCore implementation status

Measured 2026-09-30. Every number here is reproducible; nothing is carried
over from an earlier audit.

## What it is

A local tool that reads one repository, turns it into a graph in DuckDB, and
answers a plain-language question by returning a ranked bundle of real source.
A FastAPI dashboard shows the graph and the answer; `astra` does the same from
a terminal.

```
RepositoryScanner -> ParserRegistry -> import_resolver -> DuckDB -> context stack -> dashboard / CLI
```

## Measured

On this repository, 140 files:

| | |
|---|---|
| index | 1.9s (85 files/s) |
| index, 3,000 files | 11s (266 files/s) |
| query | 67ms median |
| ranking accuracy, 12 real questions | 11/12 first place, 12/12 top three |
| pack carrying source, 4k budget | 9 of 13 nodes |
| source per 8x budget | 7.9x |

| Gate | |
|---|---|
| `pytest tests/ -q` | 257 passed, 1 skipped |
| `ruff check astra/ tests/ dashboard_app.py` | clean |
| `mypy astra/ dashboard_app.py` | clean, 95 files |
| Linux + Windows, Python 3.11 and 3.12 | CI |

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
- **Tree-sitter needs a cache directory.** With neither `HOME` nor
  `XDG_CACHE_HOME`, grammars cannot be downloaded and non-Python parsing is
  skipped rather than failing.
- **BLIND_MAX depth.** Source nested past ~900 levels is skipped.

## Removed

Modules with no caller outside their own tests were deleted (46 modules,
~2,800 lines). The `backup/dead-code` branch holds the state before the
removal. Kept: `astra/cli` (the console script), `astra/patch/analyzer`
(reachable from `dashboard_app.py`), `astra/core/config.py`.

If something in that set is wanted again, restore the branch rather than
rewriting it.