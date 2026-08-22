# SAS: Phase 2 Universal Parser Engine

## Mission

Convert `RepositoryIndex` entries into language-agnostic structural and semantic nodes for graph construction.

## Input

- `RepositoryIndex` from Phase 1

## Output

- `ParseIndex`
- `ParsedFile`
- `StructuralElement`
- `DependencySignal`
- `ParserFailure`

## Requirements

- Modular parser dispatch per language.
- Streaming file-by-file parsing.
- No full repository source loading.
- Graceful fallback for unsupported languages.
- Markdown parsing for vault-oriented semantics.
- Config parsing for JSON/YAML/XML/TOML style files.
- Failure isolation per file.

## Strict Rules

- Parser consumes `RepositoryIndex`; it must not scan the repository.
- Parser may read only the current file being parsed.
- Unsupported languages must produce fallback structural metadata, not crashes.
