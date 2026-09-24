# Phase 6: Dependency Graph and Incremental Recalculation

Plan: [index.md](index.md)
Tasks: 17-18
Depends on: Phase 5 / Tasks 14-16

## Objective

Make dependency relationships first-class and implement targeted invalidation
and recomputation with cycle protection and instrumentation.

## Files to Change

| Path | Action | Required change |
|------|--------|-----------------|
| `src/andromeda_core/domain/dependencies.py` | create | Graph traversal/cycle contracts. |
| `src/andromeda_core/application/dependency_service.py` | create | Invalidate/recompute orchestration. |
| `src/andromeda_core/presentation/api/admin/derived.py` | modify | Invalidation/recompute diagnostics. |
| `tests/unit/test_dependencies.py` | create | Reverse lookup/cycles. |
| `tests/integration/test_incremental_recalculation.py` | create | Rule replacement affects only dependent results. |

## Task 17: Implement dependency graph and invalidation

### Intent

Find affected derived nodes instead of recalculating the entire knowledge base.

### Implementation Steps

1. Define a directed graph of source nodes (`fact`, `relation`, `rule`,
   `ontology`) to derived nodes and derived-to-derived edges.
2. Implement reverse traversal with visited-set and maximum depth/node guards.
3. On fact/relation/rule/ontology change, mark affected derived values
   INVALIDATED with reason and audit event.
4. Reject cycles when registering dependency edges; expose `DEPENDENCY_CYCLE`.
5. Keep invalidation inside the same transaction as rule/ontology activation
   and dependency registration.

### Required Interfaces and Contracts

- `invalidate(source_kind, source_id) -> InvalidationReport` returns affected
  and invalidated node IDs.
- Traversal order is deterministic by node kind/id.
- No global “invalidate all” fallback for a targeted mutation.

### Error Handling and Logging

Cycle or graph corruption is ERROR with source/target IDs, never an infinite
loop. Log affected count, invalidated count, duration and correlation ID.

### Tests

- A fact change invalidates only results that depend on that fact.
- Rule v2 invalidates results tied to rule v1; unrelated university results stay valid.
- Artificial cycle registration is rejected.

### Acceptance Criteria

Scenario E marks the old derived result invalid after replacement activation.

### Verification

- `pytest -q tests/unit/test_dependencies.py tests/integration/test_incremental_recalculation.py -k invalidate`

## Task 18: Add incremental recomputation instrumentation

### Intent

Recompute only required invalidated projections and make the result observable.

### Implementation Steps

1. Add a recompute service that accepts a derived result key/context and
   invokes the existing Rule Engine; do not fork the evaluator.
2. Record `affected_nodes`, `invalidated_nodes`, `recomputed_nodes`, duration,
   engine version and correlation ID in an instrumentation result/audit event.
3. Expose diagnostics in evaluation response and an admin read endpoint.
4. Ensure recompute errors leave the previous invalidated projection intact and
   return a retryable error.

### Required Interfaces and Contracts

- Recompute is idempotent and safe to retry.
- Cache/materialization is always derivable from current canonical data.
- No external Redis is required; optional cache is a future adapter.

### Error Handling and Logging

`RECOMPUTATION_FAILED` returns stable code; log exception server-side with
result/source IDs and duration. Metrics increment on failure.

### Tests

- Replacement rule recomputes changed result and records counts.
- Repeated recompute does not create duplicate derived rows.
- A failed recompute does not mark a stale result valid.

### Acceptance Criteria

Incremental metrics are present in API response/logs and show targeted work.

### Verification

- `pytest -q tests/integration/test_incremental_recalculation.py`

## Phase Risks and Mitigations

- Risk: dependency graph grows without bounds. Mitigation: indexed source
  lookup, bounded traversal and measured benchmark.
- Risk: concurrent invalidation/recompute races. Mitigation: row version/status
  checks and stable transaction ordering.

## Phase Completion Checklist

- Tasks 17-18 pass cycle/invalidation/recompute tests.
- `index.md` task statuses are updated.
