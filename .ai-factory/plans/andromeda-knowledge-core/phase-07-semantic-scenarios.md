# Phase 7: Semantic API, Applicant Context and What-If Scenarios

Plan: [index.md](index.md)
Tasks: 19-20
Depends on: Phase 6 / Tasks 17-18

## Objective

Expose a stable consumer-facing Semantic API that hides database structure,
supports applicant/query context, what-if overlays and comparison/explanation.

## Files to Change

| Path | Action | Required change |
|------|--------|-----------------|
| `src/andromeda_core/domain/semantic.py` | create | Semantic command/result contracts. |
| `src/andromeda_core/application/semantic_service.py` | create | Evaluate/simulate/compare use cases. |
| `src/andromeda_core/presentation/api/semantic/routes.py` | create | Stable `/api/v1/semantic` routes. |
| `tests/integration/test_semantic_scenarios.py` | create | Evaluate/what-if/acceptance flows. |

## Task 19: Implement applicant/query context and evaluate operations

### Intent

Keep global knowledge separate from per-request applicant context while giving
future Andromeda clients a stable contract.

### Implementation Steps

1. Define typed `ApplicantContext` fields for scores, achievements,
   olympiads, preferences, interests and constraints with extensible validated
   data for future ontology-defined properties.
2. Define `QueryContext` for campaign/year/program/scope and as-of timestamps.
3. Implement `POST /api/v1/semantic/evaluate` to load canonical facts/rules,
   call the application computation service, optionally materialize a result,
   and return score/eligibility/benefits/trace summary.
4. Implement stable read operations for program, curriculum, requirements and
   compare where demo knowledge supports them; return explicit not-found or
   unsupported semantics rather than leaking DB tables.

### Required Interfaces and Contracts

- Applicant context need not be persisted; request defaults to ephemeral.
- The response contains `result_id`, `derived_type`, `value`, `matched_rules`,
  `explanation_summary`, `engine_version`, `ontology_version` and timestamps.
- Consumer API has no rule/ontology activation capability.

### Error Handling and Logging

Invalid context/property types return `VALIDATION_FAILED`. Log scope, result
type and duration but not exam scores/preferences.

### Tests

- Evaluate demo applicant with 84 score returns base/no bonus.
- Applicant data overrides only request context; global facts remain unchanged.
- Semantic reader cannot call admin activation routes.

### Acceptance Criteria

Future clients can evaluate without knowing SQLAlchemy models or table names.

### Verification

- `pytest -q tests/integration/test_semantic_scenarios.py -k evaluate`

## Task 20: Implement overlay simulation and comparisons

### Intent

Support what-if analysis by overlaying values in memory and returning before,
after, delta and explanations without mutating persisted facts.

### Implementation Steps

1. Define `POST /api/v1/semantic/simulate` with `base_context`, typed
   `overrides`, optional query context and materialization flag disabled by
   default.
2. Run the same Rule Engine twice: base context and overlay context; use an
   immutable merge that records overridden properties.
3. Return before/after values, numeric/structured delta, matched rule changes,
   trace/explanation for both and `persisted_changes: []`.
4. Add compare-programs/eligibility result helpers over stable semantic
   contracts, not repositories exposed to clients.

### Required Interfaces and Contracts

- Overlay cannot modify ORM/domain fact collections; tests compare snapshots.
- Unsafe override paths are rejected; only ontology/applicant context paths are
  accepted.
- Simulation uses the same engine version/rule snapshot metadata as evaluation.

### Error Handling and Logging

Invalid override returns `INVALID_OVERLAY`; log count/property names only.
Timeouts return `SIMULATION_FAILED` and leave canonical data untouched.

### Tests

- Physics 84 → 94 changes result from no bonus to +30.
- Simulation response contains before/after/delta and matched rule IDs.
- Database facts and derived rows are unchanged unless explicit materialization
  is requested.

### Acceptance Criteria

Scenario F works through Swagger and automated integration tests.

### Verification

- `pytest -q tests/integration/test_semantic_scenarios.py`

## Phase Risks and Mitigations

- Risk: user context leaks into logs/persistence. Mitigation: typed redaction,
  request-scoped memory and explicit persistence flag.
- Risk: semantic API becomes a thin table CRUD mirror. Mitigation: response
  schemas are operation-oriented and do not expose database IDs except stable
  semantic/result IDs needed for follow-up.

## Phase Completion Checklist

- Tasks 19-20 pass evaluate and what-if acceptance tests.
- `index.md` task statuses are updated.
