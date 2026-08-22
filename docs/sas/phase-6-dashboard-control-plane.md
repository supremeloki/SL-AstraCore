# SAS: Phase 6 Dashboard And Control Plane

## Mission

Expose project state, graph state, context state, runtime execution state, and telemetry through a control-plane data API.

## Output

- `DashboardSystem`
- graph view state
- context inspection state
- execution control state
- telemetry metrics

## Event Types

- `SCAN_STARTED`
- `SCAN_PROGRESS`
- `GRAPH_UPDATED`
- `CONTEXT_BUILT`
- `EXECUTION_STARTED`
- `EXECUTION_STEP_COMPLETED`
- `EXECUTION_FAILED`
- `EXECUTION_REPLAYED`

## Strict Rules

- Dashboard observes and controls through public domain APIs.
- Dashboard must not mutate graph internals directly.
