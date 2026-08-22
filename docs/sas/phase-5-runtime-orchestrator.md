# SAS: Phase 5 Runtime Orchestrator

## Mission

Execute tasks using context packs while managing planning, tool mapping, validation, and recovery.

## Pipeline

Understand -> Plan -> Execute -> Verify -> Recover

## Modes

- analysis
- planning
- execution
- recovery

## Output

- `RuntimeTaskResult`
- execution plan
- verification report
- recovery plan

## Strict Rules

- No execution without context.
- Every action must have a validation step.
- Failures must return recovery instructions.
