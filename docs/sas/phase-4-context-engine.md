# SAS: Phase 4 Context Engine

## Mission

Convert a large knowledge graph into minimal, high-signal, task-specific context packs.

## Input

- `KnowledgeGraph`
- `RepositoryIndex`
- task/query text

## Output

- `ContextPack`
- `ContextGraphSlice`

## Requirements

- Query analysis.
- Graph seed selection.
- Controlled graph expansion.
- Relevance scoring.
- Filtering.
- Token budgeting.
- Agent-neutral packaging.

## Strict Rules

- Never include the full repository.
- Never include unrelated graph sections.
- Never exceed context budget when a budget is configured.
- Preserve critical dependencies and conflicts.
