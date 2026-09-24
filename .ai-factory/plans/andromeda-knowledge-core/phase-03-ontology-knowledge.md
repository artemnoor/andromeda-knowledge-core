# Phase 3: Ontology and Knowledge Ingestion

Plan: [index.md](index.md)
Tasks: 7-9
Depends on: Phase 2 / Tasks 4-6

## Objective

Implement versioned ontology, logical objects/relations, sources,
observations-to-facts promotion, provenance, confidence, unknown-concept
proposals, change detection and review queue behavior.

## Files to Change

| Path | Action | Required change |
|------|--------|-----------------|
| `src/andromeda_core/domain/ontology.py` | create | Version/status/change invariants. |
| `src/andromeda_core/domain/knowledge.py` | create | Typed fact/relation/object contracts. |
| `src/andromeda_core/domain/review.py` | create | Review reasons and transitions. |
| `src/andromeda_core/application/ontology_service.py` | create | Ontology use cases. |
| `src/andromeda_core/application/knowledge_service.py` | create | Source/observation/fact flow. |
| `src/andromeda_core/presentation/api/admin/ontology.py` | create | Ontology/proposal routes. |
| `src/andromeda_core/presentation/api/admin/knowledge.py` | create | Object/relation/fact/source/observation routes. |
| `src/andromeda_core/presentation/api/admin/reviews.py` | create | Review queue routes. |
| `tests/integration/test_knowledge_flow.py` | create | Source → Observation → Fact and unknown concept scenarios. |

## Task 7: Build versioned ontology and proposal workflow

### Intent

Prevent semantic drift and ensure ingestion cannot silently change production
meaning.

### Implementation Steps

1. Define `OntologyVersion` statuses DRAFT, VALIDATING, ACTIVE, SUPERSEDED,
   and change types BACKWARD_COMPATIBLE, BREAKING, MIGRATION_REQUIRED.
2. Define object types, property definitions (typed values) and relation types
   with allowed source/target types, cardinality and constraints.
3. Require a previous version for non-initial versions and store migration
   requirements and activation timestamps.
4. When an observation references an unknown type/property/relation, create an
   `OntologyChangeProposal` and a review item with `UNKNOWN_CONCEPT`; do not
   alter active ontology.
5. Require reviewer/admin role for proposal approval and ontology activation.

### Required Interfaces and Contracts

- Activation is atomic with ontology status update and audit event.
- Existing ontology versions are immutable after activation; a new version is
  created for semantic changes.
- A proposal lifecycle is `PROPOSED → VALIDATING → APPROVED/REJECTED/MODIFIED
  → MIGRATING → ACTIVE`.

### Error Handling and Logging

Ontology mismatch returns `ONTOLOGY_MISMATCH` and a review ID when a proposal
was created. Log proposal creation at INFO with IDs, confidence and source ID;
never log raw document content.

### Tests

- Unknown `RegionalEducationalCoefficient` creates exactly one proposal and
  review item on duplicate ingestion.
- Breaking proposal cannot activate without migration status.
- Silent mutation of an active version is rejected.

### Acceptance Criteria

The demo unknown-concept scenario produces `UNKNOWN_CONCEPT → proposal →
NEEDS_REVIEW`, and the active ontology remains unchanged.

### Verification

- `pytest -q tests/integration/test_knowledge_flow.py -k unknown`

## Task 8: Implement source, observation, fact and relation flow

### Intent

Enforce the ingestion pipeline separation: adapters emit observations, and
only a validated application use case can accept a fact.

### Implementation Steps

1. Add `Source`/`SourceDocument` schemas with conceptual types WEB_PAGE, PDF,
   API, DOCUMENT, MANUAL and IMPORT, checksum, external identity, publisher,
   retrieval and parser metadata.
2. Define the `SourceAdapter` port and deterministic/mock adapter; adapters
   return observation candidates, never facts.
3. Persist observations with RAW/PARSED/MAPPED/VALIDATED/ACCEPTED/REJECTED/
   NEEDS_REVIEW states, evidence locator and confidence status.
4. Validate observation candidates against active ontology; accept only mapped,
   sufficiently confident, non-conflicting observations via a provenance record.
5. Create typed facts or first-class relations with valid/transaction times.
6. Detect `NEW_FACT`, `FACT_CHANGED`, `FACT_REMOVED`, `NEW_RELATION`,
   `RELATION_CHANGED`, `UNKNOWN_CONCEPT` and `CONFLICT` change classifications.

### Required Interfaces and Contracts

- `POST /observations` is idempotent by source/checksum/external identifier.
- `POST /observations/{id}/accept` is reviewer/editor controlled and creates a
  fact in one transaction with provenance and audit event.
- `Fact` never has a `derived` flag that could confuse it with DerivedValue.

### Error Handling and Logging

Low confidence, conflicting source or failed validation produces a review item
with a safe reason. Accepted fact logs include fact/source/observation IDs and
classification, not the full value payload if applicant-sensitive.

### Tests

- Source → observation → accepted fact yields explainable provenance.
- Replaying the same document does not duplicate facts.
- Invalid relation source/target types are rejected.
- Valid and transaction time query paths return different expected rows.

### Acceptance Criteria

Scenario A is executable through Swagger and API tests without writing facts
from the parser adapter directly.

### Verification

- `pytest -q tests/integration/test_knowledge_flow.py`

## Task 9: Add review queue, audit and admin knowledge endpoints

### Intent

Expose safe administration boundaries so review decisions are explicit,
traceable and not mixed into Semantic API consumers.

### Implementation Steps

1. Add CRUD/read endpoints under `/api/v1/ontology`, `/objects`, `/relations`,
   `/facts`, `/sources`, `/observations`, `/reviews`, `/changes` and `/audit`.
2. Add review approve/reject/modify routes that call application services,
   record actor/reason/before/after/correlation ID and enforce role policy.
3. Add cursor pagination for list endpoints and filters used by review and
   temporal queries.
4. Add OpenAPI descriptions/examples/error responses for each route.

### Required Interfaces and Contracts

- `GET /reviews` returns reason/status/confidence/source/entity references.
- `POST /reviews/{id}/modify` takes a typed modification proposal; it cannot
  directly activate a rule or ontology version.
- `GET /audit` is read-only and returns append-only events.

### Error Handling and Logging

Unauthorized mutation returns `FORBIDDEN`; stale review version returns
`CONCURRENT_MODIFICATION`. All decisions emit an audit event.

### Tests

- Reader can list but cannot approve.
- Reviewer can approve a low-confidence fact and audit event is persisted.
- Cursor pagination is stable and does not use unbounded offset.

### Acceptance Criteria

The admin/domain API is conceptually distinct from `/semantic` and Swagger
shows usable descriptions/examples.

### Verification

- `pytest -q tests/integration/test_knowledge_flow.py`
- Inspect `/openapi.json` for the admin route groups and error schema.

## Phase Risks and Mitigations

- Risk: direct fact endpoint bypasses provenance. Mitigation: require a
  provenance record or return `MISSING_PROVENANCE`.
- Risk: ingestion creates duplicate proposals under concurrency. Mitigation:
  unique natural key and atomic upsert.

## Phase Completion Checklist

- Tasks 7-9 pass source/observation/fact, unknown concept and review scenarios.
- Admin routes enforce role boundary and audit decisions.
- `index.md` task statuses are updated.
