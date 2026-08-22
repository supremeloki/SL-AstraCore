# SAS: Phase 7 Agent Adapter Layer

## Mission

Make multiple execution agents interchangeable by adapting context, requests, responses, routing, retries, and tool bridges.

## Input

- `ContextPack`
- `ExecutionPlan`
- `KnowledgeGraph`

## Output

- `AgentExecutionResult`

## Requirements

- Agent registry.
- Context format adapters.
- Request builder.
- Response normalizer.
- Routing engine.
- Fallback/retry engine.
- Tool bridge.
- Security and validation boundary.

## Strict Rules

- Agents cannot modify graph directly.
- Agents cannot bypass the orchestrator.
- Context adaptation may transform format only; it must not drop semantic meaning.
- All outputs must be normalized and validated.
