# Phase 5: Rule Engine, Derived Knowledge and Explainability

Plan: [index.md](index.md)
Tasks: 14-16
Depends on: Phase 4 / Tasks 10-13

## Objective

Create the universal deterministic Rule Engine and persist derived results,
execution traces and explanation chains without treating derived values as
facts.

## Files to Change

| Path | Action | Required change |
|------|--------|-----------------|
| `src/andromeda_core/domain/engine.py` | create | Pure evaluation accumulator and result. |
| `src/andromeda_core/domain/derived.py` | create | Derived value/trace/dependency contracts. |
| `src/andromeda_core/application/computation_service.py` | create | Load rules/facts, execute and materialize. |
| `src/andromeda_core/application/explain_service.py` | create | Expand trace to provenance/source chain. |
| `src/andromeda_core/presentation/api/admin/derived.py` | create | Derived read endpoints. |
| `src/andromeda_core/presentation/api/semantic/evaluate.py` | create | Consumer evaluation/explain operations. |
| `tests/unit/test_rule_engine.py` | create | Determinism, traces and effects. |
| `tests/integration/test_explainability.py` | create | Derived → rule → fact → observation → source. |

## Task 14: Implement pure Rule Engine

### Intent

Turn Facts + Ontology + Rules + Context into deterministic derived knowledge
without admission-specific code.

### Implementation Steps

1. Define `EvaluationInput` containing typed facts, relations, ontology view,
   active rule versions, applicant context, query context, overlay and engine
   version.
2. Evaluate active rules in stable `(priority desc, logical_key, version)`
   order, applying scope, condition and exception checks.
3. Dispatch validated effects via the registry; accumulate scalar targets,
   grants, denials, eligibility flags and emitted derived values.
4. Produce `EvaluationResult` with result type/value, matched rules, skipped
   rules, dependencies, trace nodes, explanation text and engine metadata.
5. Include `engine_version`, ontology version and exact rule version IDs in the
   result hash/metadata.

### Required Interfaces and Contracts

- Same input snapshot produces byte-equivalent canonical result and trace.
- An inactive/superseded rule cannot produce an effect.
- Unknown fact values are represented as absent/unknown, not silently zero.
- Every matched effect records supporting fact/relation IDs and rule ID.

### Error Handling and Logging

DSL errors should have been rejected before execution; runtime type mismatch
returns `EVALUATION_FAILED` with a rule ID and trace node. Emit duration and
matched-rule count, never raw applicant context.

### Tests

- Demo fourth exam at 89/90/100 yields 0/30/30.
- Same input twice yields same canonical output.
- Overlay changes evaluation input only and leaves base facts unchanged.
- Benefit rule with at least 2 of 3 conditions works without a handler.

### Acceptance Criteria

The engine is unaware of BMSTU, fourth exams and admission years; all demo
behavior arrives from rule/ontology data.

### Verification

- `pytest -q tests/unit/test_rule_engine.py`

## Task 15: Materialize Derived Knowledge and dependencies metadata

### Intent

Make computed knowledge inspectable, cacheable and invalidatable while keeping
the source of truth in canonical facts/rules.

### Implementation Steps

1. Persist `DerivedValue` with type, value, query/applicant context snapshot,
   status (`VALID`, `INVALIDATED`), computed time, engine/ontology/rule version
   metadata and execution trace.
2. Upsert by a canonical result key only when the same snapshot/version set is
   being requested; never overwrite a primary fact.
3. Persist dependencies from each fact/relation/rule to the derived result.
4. Add read routes for derived values and trace metadata.

### Required Interfaces and Contracts

- Derived values are rebuildable projections; deleting them never deletes facts.
- Applicant context is stored only with explicit persistence request and is
  redacted/limited to the evaluation snapshot needed for explanation.
- Results include invalidation reason and recomputation metadata.

### Error Handling and Logging

Duplicate materialization is idempotent. Log derived ID, result type,
dependency count and duration. Do not log full context/value blobs.

### Tests

- Derived row is distinct from fact row.
- Dependencies include all matched rules and supporting facts.
- Re-evaluation after invalidation creates a valid replacement projection.

### Acceptance Criteria

Consumer evaluation returns a stable result ID that can be explained later.

### Verification

- `pytest -q tests/integration/test_explainability.py -k material`

## Task 16: Implement explainability chain

### Intent

Provide machine-readable and human-readable reason reconstruction.

### Implementation Steps

1. Load derived trace/dependency records.
2. Expand rule IDs to rule versions and fact/relation IDs to canonical records.
3. Expand fact/relation provenance to observations, evidence locators and
   sources; preserve missing evidence as explicit unknown nodes.
4. Return a tree/graph JSON shape with node IDs, kinds, labels, values,
   confidence/status and child links plus a concise explanation.

### Required Interfaces and Contracts

- `GET /api/v1/semantic/explain/{result_id}` is read-only and stable for future
  clients.
- The chain is `derived → rule → fact/relation → observation → source`.
- Explanation never claims a source when provenance is absent; it returns
  `MISSING_PROVENANCE` metadata instead.

### Error Handling and Logging

Unknown result returns `NOT_FOUND`; broken provenance is a warning/audit signal,
not a fabricated source. Log result ID and node count.

### Tests

- Demo admission score explanation includes source URL, observation and fact.
- Machine-readable nodes have stable kinds/IDs.
- Missing provenance is represented safely.

### Acceptance Criteria

Scenario D is demonstrable from Swagger in one request after evaluation.

### Verification

- `pytest -q tests/integration/test_explainability.py`

## Phase Risks and Mitigations

- Risk: traces become unbounded. Mitigation: bounded recursion, summarized
  skipped rules and configurable max trace nodes.
- Risk: derived cache becomes source of truth. Mitigation: explicit status and
  repository APIs that never satisfy fact queries from derived rows.

## Phase Completion Checklist

- Tasks 14-16 pass deterministic engine, materialization and explain tests.
- `index.md` task statuses are updated.
