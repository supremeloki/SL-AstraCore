# SL-AstraCore implementation status

Measured 2026-10-01. Every number below was re-measured against this tree.

## What it is

A local tool that reads one repository, turns it into a graph in DuckDB, and
answers a plain-language question by returning a ranked bundle of real source.
A FastAPI dashboard shows the graph and the answer; `astra` does the same from
a terminal; `astra propose` turns a model's reply into a reviewed edit.

```
RepositoryScanner -> ParserRegistry -> import_resolver -> DuckDB -> context stack -> dashboard / CLI
                                                                        ↓
                                                        astra/agent: review -> apply
```

95 modules, 9,394 lines under `astra/`, plus `dashboard_app.py`.

## Measured

| | |
|---|---|
| index this repository (172 files) | 1.4s (120 files/s) |
| re-index, nothing changed | 0.36s |
| index 3,000 files | 7.5s (402 files/s) |
| query | 62ms median |
| ranking accuracy, 12 real questions | 11/12 first place, 12/12 top three |
| pack carrying source, 4k budget | 8 of 13 nodes |
| source per 8x budget | 8.0x |
| test coverage | 88% of statement lines, no file at zero |

| Gate | |
|---|---|
| `pytest tests/ -q` | 331 passed, 1 skipped |
| `ruff check astra/ tests/ dashboard_app.py` | clean |
| `mypy astra/ dashboard_app.py` | clean, 96 files |
| Linux + Windows, Python 3.11 and 3.12 | green |

## The agent loop

`astra/agent` connects the pack builder, the AST differ and the risk scorer,
which all existed but were wired to nothing.

    question -> pack -> model -> proposed edit -> parsed diff -> risk
             -> the caller decides whether to write

The model is a callable the caller supplies, so nothing here needs a provider
account and every test runs offline. The model is never given a way to write.
An edit is refused before it can become a suggestion when its `old_text` is
not verbatim in the file it names, when the result does not parse, or when it
changes nothing. Applying is a separate command that refuses a proposal whose
file changed since the review.

Reachable as `POST /api/agent/propose`, `astra propose --emit`, and
`astra apply`.

## Deliberate limitations

- **No provider is wired in.** The loop takes a reply and reviews it; running
  a model is the caller's, because a bundled provider means an API key, a
  network dependency and a bill.
- **A re-index with one changed file is not faster.** Unchanged files are not
  parsed again, which makes a no-op re-index 3x faster, but the write still
  reads every node.
- **Conflicts are file-level.** Two modules may define the same class without
  a conflict being reported; only the same file base name in different modules
  counts.
- **Single-user access control.** A per-process token, not accounts. It binds
  all interfaces, so do not expose it beyond a trusted network. Set
  `ASTRA_TOKEN` to pin the token; there is no TLS.
- **Config keys are indexed, values are not.** `.json` / `.yaml` / `.toml` are
  parsed for their key paths, so a question about a setting finds the file
  that declares it. The values are not in the graph.
- **A question with no searchable word returns nothing.** "fix it" has no
  term in any filename; name the subject.
- **Tree-sitter needs a cache directory.** With neither `HOME` nor
  `XDG_CACHE_HOME`, grammars cannot be downloaded and non-Python parsing is
  skipped rather than failing.
- **BLIND_MAX depth.** Source nested past ~900 levels is skipped.

## Removed

Modules with no caller outside their own tests were deleted. The coverage
measurement found two more: RuntimeBrain (101 lines, zero callers) and
DomainGraphEngine (the only class in graph_engine.py, likewise). 491 lines.

They are gone from history as well as the tree — there is no branch holding
them. Kept: `astra/cli` (the console script), `astra/patch/analyzer`
(reachable from `dashboard_app.py`), `astra/core/config.py`.

If one of them is wanted again it has to be rewritten; nothing to restore from.