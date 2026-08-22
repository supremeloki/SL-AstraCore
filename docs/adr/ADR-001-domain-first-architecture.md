# ADR-001: Domain-First Project Architecture

## Status

Accepted

## Decision

SL-AstraCore source code is organized by domain, not by design layers.

Design layers remain architecture documentation. Runtime code lives under stable domain modules:

- `core`
- `scanner`
- `parser`
- `graph`
- `vault`
- `context`
- `runtime`
- `dashboard`
- `plugins`

## Rationale

Domain ownership is easier to maintain than implementation layers. Scanner, parser, graph, context, and runtime each have independent contracts, tests, and evolution paths.

## Consequences

- New implementation work must target domain packages.
- Layer terminology may appear in documentation and orchestration only.
- Engines after scanner consume the Repository Scanner contract and must not rescan the repository.
- Master prompts are treated as Software Architecture Specifications.
