# SAS: Phase 3 Knowledge Graph Engine

## Mission

Merge repository metadata and parser output into a navigable semantic graph.

## Input

- `RepositoryIndex`
- `ParseIndex`

## Output

- `KnowledgeGraph`
- graph indexes
- queryable node/edge representation

## Requirements

- Directed graph construction.
- Code, file, symbol, config, and vault nodes.
- Dependency, import, call, reference, link, and belongs-to edges.
- Incremental graph updates.
- Query support for neighbors, paths, dependencies, and subgraph extraction.

## Strict Rules

- Graph engine consumes scanner/parser outputs; it must not read the filesystem directly.
- Node IDs must be deterministic.
- Graph construction must tolerate partial parser failures.
