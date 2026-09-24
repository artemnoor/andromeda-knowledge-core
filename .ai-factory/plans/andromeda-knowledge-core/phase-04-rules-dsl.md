# Phase 4: Rules as Data, Typed DSL and Lifecycle

Plan: [index.md](index.md)
Tasks: 10-13
Depends on: Phase 3 / Tasks 7-9

## Objective

Implement a safe serializable Rule DSL, declarative effects/scopes/exceptions,
rule version lifecycle, test cases, conflict detection and atomic activation.

## Files to Change

| Path | Action | Required change |
|------|--------|-----------------|
| `src/andromeda_core/domain/dsl/ast.py` | create | Typed AST model and JSON serialization. |
| `src/andromeda_core/domain/dsl/validator.py` | create | Operator/type/reference validation. |
| `src/andromeda_core/domain/dsl/evaluator.py` | create | Pure deterministic condition evaluation. |
| `src/andromeda_core/domain/rules.py` | create | Rule lifecycle/scope/conflict contracts. |
| `src/andromeda_core/application/rule_service.py` | create | Validate/test/activate/replacement use cases. |
| `src/andromeda_core/presentation/api/admin/rules.py` | create | Rule CRUD and lifecycle endpoints. |
| `tests/unit/test_dsl.py` | create | Operators, typing and safety. |
| `tests/integration/test_rules.py` | create | Lifecycle, tests, conflicts and replacement. |

## Task 10: Define and validate the typed Rule DSL

### Intent

Let new education policy be represented as data while preserving determinism,
explainability and safety.

### Implementation Steps

1. Define JSON AST nodes for literals, fact/relation/context/applicant refs,
   logical operators AND/OR/NOT, comparison operators, exists/not_exists,
   in/not_in, count/sum/min/max and any/all/none/at_least quantifiers.
2. Define typed value kinds string, integer, decimal, boolean, date, datetime,
   enum, reference and collection.
3. Validate operators, operand arity, references, collection requirements and
   type compatibility recursively before persistence/activation.
4. Canonicalize AST JSON for hashing and deterministic trace output.
5. Reject unknown operators, extra keys where unsafe, recursive/cyclic AST
   structures, oversized nesting and non-JSON values.

### Required Interfaces and Contracts

- `validate_condition(node, ontology) -> ValidationReport` is pure.
- No `eval`, `exec`, dynamic import or user-selected Python callable is used.
- Conditions can read global facts, relations, `context` and `applicant` data.
- `at_least` is represented as a typed quantifier with integer `count` and a
  list of child predicates.

### Error Handling and Logging

Invalid DSL returns `INVALID_DSL` with JSON paths and safe operator/type
details. Do not log full applicant input during evaluation.

### Tests

- Boundary comparisons `>=`, `<`, equality and membership.
- All logical/quantifier/aggregation operators.
- Wrong property type, unknown operator, missing operand and excessive depth.
- Same AST canonical form yields same hash.
- Property-based tests verify deterministic evaluation and overlay immutability.

### Acceptance Criteria

The fourth-exam threshold and a completely different “at least 2 of 3” benefit
rule both validate without rule-specific Python handlers.

### Verification

- `pytest -q tests/unit/test_dsl.py`

## Task 11: Implement effects, scope, exceptions and rule versions

### Intent

Keep policy mechanics declarative and extensible through a registered effect
kind rather than hard-coded university logic.

### Implementation Steps

1. Define rule data with stable logical key, version, type, scope, conditions,
   effects, exceptions, priority, valid/transaction time, provenance,
   ontology version and lifecycle status.
2. Implement generic scope matching against ontology-backed context fields
   (organization, program, education level, form, campaign, year and category)
   without hard-coding named institutions.
3. Implement effect registry for SET, ADD, SUBTRACT, GRANT, DENY,
   MARK_ELIGIBLE, MARK_INELIGIBLE and EMIT_DERIVED; handlers operate on an
   engine accumulator and return trace fragments.
4. Exceptions reuse the same condition AST and prevent effects when matched.
5. Represent REPLACES, OVERRIDES, EXCLUDES and CONFLICTS_WITH relations and
   replacement/supersession links in persistence.

### Required Interfaces and Contracts

- Effects with an unknown kind are rejected at validation; adding a new generic
  effect requires registering a handler, not changing the core evaluator.
- Active rules are selected by status, valid time, transaction-time knowledge
  and scope; superseded/revoked rules never execute.
- Rules are versioned data; changing threshold only creates a new version.

### Error Handling and Logging

Unsupported effect returns `INVALID_EFFECT`. Scope mismatch is normal and is a
traceable non-match, not an error. Log activation IDs and version metadata.

### Tests

- Generic SET/ADD/SUBTRACT and benefit/eligibility effects.
- Exception suppresses an otherwise matched effect.
- Scope includes/excludes context correctly.
- Superseded rule is ignored after replacement activation.

### Acceptance Criteria

No rule engine code contains institution/year/exam-specific condition branches.

### Verification

- `pytest -q tests/unit/test_dsl.py tests/integration/test_rules.py -k 'effect or scope or exception'`

## Task 12: Add rule test cases and lifecycle operations

### Intent

Make production activation evidence-gated and reproducible.

### Implementation Steps

1. Persist rule test cases with given facts/context, expected effects and
   expected explanation fragments.
2. Implement `validate`, `test` and `activate` application operations and
   `POST /rules/{id}/validate`, `/test`, `/activate` routes.
3. Require successful DSL validation and all mandatory test cases before active
   transition; test failures leave the rule in VALIDATING/TESTING/REVIEW.
4. Use an atomic transaction for activation, replacement/supersession,
   dependency invalidation and audit event.

### Required Interfaces and Contracts

- Lifecycle: DRAFT → VALIDATING → TESTING → REVIEW → ACTIVE →
  SUPERSEDED/REVOKED.
- Activation requires reviewer/admin/system role, not reader/editor.
- Concurrency uses `row_version`; stale updates return 409.

### Error Handling and Logging

`ACTIVATION_GUARD_FAILED` includes failed test IDs/conflict review IDs without
exposing private data. Emit `RULE_VALIDATED`, `RULE_TESTED`, `RULE_ACTIVATED`
or `RULE_REJECTED` audit records.

### Tests

- Missing tests cannot activate.
- Boundary cases 89/90/100 and exception active behave as specified.
- Concurrent activation with stale version returns conflict.
- Idempotent repeated activation returns current active version.

### Acceptance Criteria

Scenario B is executable via Swagger and the activation endpoint never bypasses
validation/tests/conflicts.

### Verification

- `pytest -q tests/integration/test_rules.py`

## Task 13: Implement deterministic rule conflict detection

### Intent

Resolve only conflicts covered by explicit policy and send ambiguous normative
conflicts to human review.

### Implementation Steps

1. Compare active candidate rules by overlapping scope, validity, logical key
   and effect targets.
2. If priorities differ and policy says the higher priority wins, record a
   deterministic override trace.
3. If equal priority produces contradictory GRANT/DENY, eligibility flags or
   incompatible SET values, create a conflict review and block activation.
4. Persist `CONFLICTS_WITH` relation and audit event.

### Required Interfaces and Contracts

- Conflict detector is pure and deterministic; it does not call an LLM.
- No arbitrary “latest wins” fallback for unresolvable equal-priority rules.

### Error Handling and Logging

Blocked activation returns `RULE_CONFLICT` with both rule IDs and review ID.
Log policy decision and priority only; keep source content out of logs.

### Tests

- Different priority resolves deterministically.
- Equal-priority contradictory effects create `NEEDS_REVIEW`.
- Non-overlapping scopes do not conflict.

### Acceptance Criteria

Scenario H reaches Review Queue without a silent choice.

### Verification

- `pytest -q tests/integration/test_rules.py -k conflict`

## Phase Risks and Mitigations

- Risk: DSL grows into an unsafe programming language. Mitigation: finite AST,
  depth/size limits, typed references and a closed effect registry.
- Risk: test cases are too weak. Mitigation: require at least one test for each
  boundary branch and store expected explanation fragments.

## Phase Completion Checklist

- Tasks 10-13 pass unit/property/rule lifecycle/conflict tests.
- No Python policy branch encodes the demo threshold.
- `index.md` task statuses are updated.
