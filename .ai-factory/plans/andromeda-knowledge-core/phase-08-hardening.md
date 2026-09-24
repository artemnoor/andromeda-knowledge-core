# Phase 8: AI Ports, Security and Production Hardening

Plan: [index.md](index.md)
Tasks: 21-23
Depends on: Phase 7 / Tasks 19-20

## Objective

Make AI/source extension points explicit, secure administrative operations,
cover negative paths, improve observability and verify production boundaries.

## Files to Change

| Path | Action | Required change |
|------|--------|-----------------|
| `src/andromeda_core/domain/ports/ai.py` | create | AI/Jev port interfaces and proposal contracts. |
| `src/andromeda_core/infrastructure/adapters/mock_ai.py` | create | Deterministic mock adapters. |
| `src/andromeda_core/infrastructure/security.py` | create/modify | Role policy and request validation. |
| `tests/unit/test_ai_boundary.py` | create | Untrusted proposal/activation guard tests. |
| `tests/integration/test_negative_paths.py` | create | Invalid DSL, provenance, cycles, concurrency/security. |
| `docs/ai-boundaries.md` | create | AI safety and integration limits. |

## Task 21: Add AI/Jev ports and mock adapters

### Intent

Allow extraction, mapping and comparison assistance without making an external
model a source of truth or a runtime requirement.

### Implementation Steps

1. Define `DocumentUnderstandingPort`, `EntityResolutionPort`,
   `OntologyMappingPort`, `RuleExtractionPort` and `ChangeInterpretationPort`.
2. Define all returns as proposal/evidence DTOs with confidence and source
   locator, never canonical Fact/Rule/Ontology mutations.
3. Add deterministic mock implementations for tests and local demos.
4. Wire source ingestion to accept adapter output only through observation or
   change proposal services.

### Required Interfaces and Contracts

- AI cannot call activation operations or issue arbitrary tool commands.
- External content is delimited/sanitized before any future model adapter sees it.
- Replacing mock/Jev/LLM changes only composition adapters, not core modules.

### Error Handling and Logging

Adapter failures return `EXTERNAL_ADAPTER_FAILED`, are correlated and retried
only by the future job layer. Never log raw prompts, documents or secrets.

### Tests

- Mock extraction creates observation proposals, not facts.
- AI-suggested rule cannot activate without normal validation/tests/reviewer.
- Malicious instruction text is treated as document content, not a command.

### Acceptance Criteria

AI safety boundary is visible in code, tests and documentation.

### Verification

- `pytest -q tests/unit/test_ai_boundary.py`

## Task 22: Harden security and concurrency boundaries

### Intent

Close common API/SQL/race-condition failure modes for local production-oriented
operation.

### Implementation Steps

1. Use Pydantic v2 validation and strict allowlists for DSL/effect/override
   inputs; parameterized SQLAlchemy queries only.
2. Require role checks on admin mutations; keep reader semantic routes separate.
3. Enforce correlation-safe generic errors, body-size limits, CORS allowlist and
   security headers configurable by environment.
4. Add idempotency keys for source/observation/rule mutation operations where
   duplicate requests could create repeated knowledge.
5. Use optimistic locking on mutable versioned entities and deterministic lock
   ordering/short transactions around activation/invalidation.

### Required Interfaces and Contracts

- No authentication provider is pretended to be complete; the `X-Role` stub is
  explicitly a local boundary to replace with host identity middleware.
- Secrets only come from environment/config; error responses are client-safe.

### Error Handling and Logging

`FORBIDDEN`, `CONCURRENT_MODIFICATION`, `IDEMPOTENCY_CONFLICT` and
`VALIDATION_FAILED` are stable codes. Security-relevant decisions emit audit
events; never log auth headers or secrets.

### Tests

- SQL injection-shaped strings remain values, not SQL.
- Unauthorized activation and direct route bypass fail.
- Duplicate mutation with same key is idempotent.
- Concurrent stale version is a 409.
- Negative DSL/provenance/temporal/relation cases are covered.

### Acceptance Criteria

Security checklist has no unmitigated critical path in the tested local scope;
known deployment limitations are documented explicitly.

### Verification

- `pytest -q tests/integration/test_negative_paths.py`
- `ruff check src tests`

## Task 23: Add observability and operations documentation

### Intent

Make rule evaluation, invalidation and failure behavior diagnosable without
exposing sensitive knowledge.

### Implementation Steps

1. Add structured event names for evaluation start/end, activation, invalidation,
   recomputation, review decisions and ingestion classification.
2. Ensure metrics cover request duration, rule execution duration, invalidation
   counts, recompute counts and error counts.
3. Document log fields, correlation propagation, health/readiness, metrics and
   production auth replacement.

### Required Interfaces and Contracts

Logs are JSON lines; all events carry correlation ID and safe entity IDs.

### Error Handling and Logging

Failures include stable code and trace ID in response, detailed stack only in
server log, and metrics increment exactly once per request failure.

### Tests

- Capture JSON logs for an evaluate request and assert required fields.
- Metrics counters move for success/failure and recompute.

### Acceptance Criteria

An operator can trace one request across evaluation and recomputation using one
correlation ID.

### Verification

- `pytest -q tests/unit/test_foundation.py tests/integration/test_semantic_scenarios.py -k 'log or metric'`

## Phase Risks and Mitigations

- Risk: local role header is mistaken for production auth. Mitigation: startup
  warning in non-production docs and explicit replacement contract.
- Risk: logs contain sensitive applicant values. Mitigation: field allowlist,
  no request-body logging and redaction tests.

## Phase Completion Checklist

- Tasks 21-23 pass AI boundary/security/observability checks.
- `index.md` task statuses are updated.
