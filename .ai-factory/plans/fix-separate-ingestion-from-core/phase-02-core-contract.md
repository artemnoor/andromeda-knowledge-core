# Phase 2: Versioned Core contract and anti-corruption adapter

Plan: [index.md](index.md)
Tasks: 4-6
Depends on: Phase 1 / Tasks 1-3

## Objective

Expose only the minimal Core HTTP contracts needed by Ingestion: full ontology/Rule DSL context, source metadata and source-document metadata, and generic observation publication.

## Current-Code Evidence

| Path | Symbols / lines | Why it matters |
|---|---|---|
| `src/andromeda_core/presentation/api/admin/ontology.py` | `list_versions`, `get_version` | Existing ontology routes expose definitions but not one stable snapshot/DSL schema. |
| `src/andromeda_core/presentation/api/admin/knowledge.py` | `create_source`, `create_observation` | Existing generic publish surface is sufficient for candidate observations. |
| `src/andromeda_core/infrastructure/db/models.py` | `SourceModel`, `SourceDocumentModel` | Canonical metadata already exists; add a typed registration use case rather than sharing tables. |
| `src/andromeda_ingestion/infrastructure/knowledge_core/http.py` | `KnowledgeCoreHttpAdapter` | Existing adapter owns Core route knowledge and must be the only place that changes for route details. |

## Files to Change

| Path | Action | Required change |
|---|---|---|
| `src/andromeda_core/domain/dsl/ast.py` | modify | Export a serializable Rule DSL schema summary. |
| `src/andromeda_core/presentation/api/schemas.py` | modify | Add source-document request and ontology snapshot response models if appropriate. |
| `src/andromeda_core/presentation/api/admin/ontology.py` | modify | Add `GET /api/v1/ontology/snapshot`. |
| `src/andromeda_core/presentation/api/admin/knowledge.py`, `application/knowledge_service.py`, repository port/adapter | modify | Add idempotent source-document registration. |
| `src/andromeda_ingestion/domain/contracts.py`, `domain/ports/knowledge_core.py` | modify | Add typed source registration result. |
| `src/andromeda_ingestion/infrastructure/knowledge_core/http.py`, `mock.py` | modify | Implement the versioned adapter and deterministic mock. |

## Task 4: Add ontology snapshot contract

### Intent

Let Ingestion retrieve the active object types, properties, relations, Rule DSL schema and ontology version without importing Core domain/ORM code.

### Implementation Steps

1. Add a pure `rule_dsl_schema()`/constant near `ALLOWED_KINDS`, operator sets and effect types that returns JSON-safe sorted values and a schema version.
2. Add `GET /api/v1/ontology/snapshot` to the Core ontology router. Read the active ontology; if none exists return a valid empty snapshot with `ontology_version_id: null`. If active exists, merge `ontology_definitions` and DSL schema.
3. Use a response model or stable documented JSON shape with `schema_version`, `ontology_version_id`, `version_code`, `object_types`, `properties`, `relation_types`, `rule_dsl_schema`.
4. Change `KnowledgeCoreHttpAdapter.get_ontology_snapshot` to call only this endpoint and validate the full `OntologySnapshot` model. Convert 4xx/5xx/invalid JSON to `UpstreamError` with URL/status metadata and no body leakage.

### Required Interfaces and Contracts

- `GET /api/v1/ontology/snapshot` is read-only and uses the existing default reader role.
- `relation_types` is the canonical field name on the wire; ingestion may normalize aliases only at its own adapter seam.
- The snapshot is context for untrusted AI extraction, not an instruction to Core or an activation command.

### Error Handling and Logging

- Missing active ontology is a valid empty response, not a 500.
- Adapter logs only endpoint, status and correlation-safe identifiers; never API tokens or full payloads.

### Tests

- Core acceptance test asserts a seeded snapshot includes object types, properties, relations and a DSL schema.
- Ingestion adapter MockTransport test asserts the exact endpoint and typed parsing.

### Acceptance Criteria

- A real ingestion adapter can construct `ExtractionContext.ontology` from one Core request.

### Verification

- `pytest -q tests/integration/test_acceptance.py tests/api/test_api_contract.py` in Core.
- Expected result: snapshot route is present in OpenAPI and returns the complete shape.

## Task 5: Add source-document registration

### Intent

Allow Ingestion to register immutable artifact metadata in Core without sending raw bytes or relying on an invalid foreign-key placeholder.

### Implementation Steps

1. Add `SourceDocumentCreate` with `source_id`, `document_checksum`, title, content metadata and retrieved timestamp.
2. Add repository/application methods to find by `(source_id, document_checksum)` and return the existing row or create/commit a new `SourceDocumentModel`.
3. Add `POST /api/v1/source-documents` requiring `EDITOR`; verify the source exists and return the typed row. Preserve idempotency on repeated checksum.
4. Update Core docs and OpenAPI tests.

### Required Interfaces and Contracts

- The endpoint receives metadata only: artifact ID/location, canonical/final URL, content type, byte size, checksum, retrieval time and parser version are allowed; body bytes are forbidden.
- Response contains `id` used as `ObservationCreate.source_document_id`.

### Error Handling and Logging

- Unknown source returns the existing stable `NOT_FOUND` error.
- Duplicate `(source_id, checksum)` returns the existing document, not a second row.
- Logs record source/document IDs and checksum prefix only.

### Tests

- Core integration test posts the same document twice and asserts one ID.
- Ingestion HTTP adapter test verifies two calls on first registration and idempotent response mapping.

### Acceptance Criteria

- `KnowledgeCoreHttpAdapter` can publish an observation with a valid Core source-document ID.
- No raw artifact body is included in the request.

### Verification

- Core `pytest -q` and an adapter MockTransport test.

## Task 6: Adapt the Ingestion Core port

### Intent

Keep route details and payload mapping behind one deep `KnowledgeCorePort` seam so Core API evolution does not leak into extraction/application modules.

### Implementation Steps

1. Add `SourceRegistration` to ingestion contracts with `source_id` and `source_document_id`.
2. Change `KnowledgeCorePort.register_source` to return `SourceRegistration`; implement source upsert with stable `external_identifier=source.stable_key`, then source-document registration with artifact checksum.
3. Update `PublishingService` to use `registration.source_id` and `registration.source_document_id`, mapping candidate evidence/artifact references without importing Core types.
4. Update `MockKnowledgeCoreAdapter`, tests and ADR 0006.

### Required Interfaces and Contracts

- `KnowledgeCorePort` exposes only `get_ontology_snapshot`, `register_source`, `publish_observation`.
- Candidate rules/relations/unknown concepts/change candidates continue through the existing generic observation envelope and remain reviewable; no direct fact/rule activation is added.
- Idempotency key remains stable per candidate and correlation ID is forwarded.

### Error Handling and Logging

- Any failed source-document or observation request raises `UpstreamError` and leaves ingestion candidate state retryable.
- Do not catch and convert Core validation errors into successful publish results.

### Tests

- Existing Core outage test must continue to leave extraction/candidates persisted.
- Adapter tests must assert no ORM import and no shared database call.

### Acceptance Criteria

- `rg` in `andromeda_ingestion/src` finds no `andromeda_core` import except none; all Core knowledge is accessed through the port adapter.

### Verification

- `ruff check src tests alembic scripts` and `mypy src` in Ingestion.

## Phase Risks and Mitigations

- Risk: existing external Core deployments lack the new route. Mitigation: document the contract version and fail explicitly; do not silently send raw bytes or bypass the adapter.
- Risk: source identity changes create duplicate Core sources. Mitigation: use stable source external identity and checksum-scoped SourceDocument rows.
