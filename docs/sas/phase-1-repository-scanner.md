# SAS: Phase 1 Repository Scanner

## Mission

Design and implement a production-grade repository scanner capable of indexing large software projects without exhausting memory.

## Contract

Input:

- Repository root

Output:

- `RepositoryIndex`
- `RepositoryTree`
- `ScanMetadata`
- `FileMetadata`
- `LanguageSummary`
- failure report

Large repositories may consume the contract through `scan_iter()` or JSONL export to avoid holding the full file list in memory.

## Requirements

- Streaming traversal
- Incremental scan
- Checkpoint support
- Resume interrupted scan
- Parallel metadata extraction
- Configurable ignore rules
- Symlink handling
- Permission handling
- Hidden files support
- Cross-platform deterministic output
- Deterministic file ID for every indexed file

## Domain Tree

```text
Repository Scanner

ROOT
|
|-- Scanner Core
|-- Filesystem Walker
|-- Ignore Engine
|-- Language Detector
|-- Binary Detector
|-- Metadata Extractor
|-- Hash Engine
|-- Repository Index Builder
|-- Checkpoint Engine
|-- Resume Engine
|-- Statistics Engine
|-- Error Handler
|-- Logger
`-- Export Engine
```

## Strict Rules

- No recursive memory accumulation during traversal.
- No full project loading during scanning.
- No token-based storage.
- No assumptions about file readability.
- Every file receives a deterministic ID.
- Engines after scanner consume `RepositoryIndex` and do not scan the filesystem again.
