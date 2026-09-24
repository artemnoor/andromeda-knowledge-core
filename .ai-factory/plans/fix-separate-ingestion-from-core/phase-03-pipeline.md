# Phase 3: Refreshable and resumable Ingestion pipeline

Plan: [index.md](index.md)
Tasks: 7-9
Depends on: Phase 2 / Tasks 4-6

## Objective

Make the existing Ingestion pipeline re-check terminal sources while preserving artifacts/extractions and resume exactly from the stage that failed.

## Current-Code Evidence

| Path | Symbols / lines | Why it matters |
|---|---|---|
| `application/orchestration/service.py` | `PipelineOrchestrator.run`, `_transition` | Current implementation returns terminal rows and always starts retryable rows at FETCHING. |
| `domain/pipelines/state.py` | `ALLOWED_TRANSITIONS` | State policy must permit terminal refresh and stage-local retry. |
| `application/fetching/service.py` | `fetch_item` | Already computes checksum and stores immutable artifact versions; orchestrator must use its unchanged flag correctly. |
| `application/extraction/service.py`, `validation/use_case.py`, `publishing/service.py` | persisted extraction/candidate stages | These are the durable restart seams; do not reimplement them in Core. |

## Files to Change

| Path | Action | Required change |
|---|---|---|
| `domain/pipelines/state.py` | modify | Permit terminal refresh and retry-to-validation if needed. |
| `application/orchestration/service.py` | modify | Add refresh branch, stage-aware resume, safe state transitions and logging. |
| `domain/contracts.py`, `infrastructure/db/models.py`, `infrastructure/db/repositories/sqlalchemy.py` | modify only if needed | Keep persisted pipeline representation aligned; no raw bytes in pipeline row. |
| `docs/ingestion-pipeline.md` | modify | Document actual refresh/resume sequence. |

## Task 7: Make terminal runs refreshable

### Intent

Prevent a stable source/item/profile idempotency key from becoming a permanent cache hit.

### Implementation Steps

1. In `PipelineOrchestrator.run`, for `PUBLISHED`/`SKIPPED_UNCHANGED`, transition the existing run to `FETCHING`, clear current attempt artifact/extraction references only when beginning a changed attempt, and invoke `FetchService.fetch_item` again.
2. Transition to `FETCHED` with the returned artifact. If `unchanged` is true, transition to `SKIPPED_UNCHANGED` without preparation/AI/validation/publish.
3. If checksum changed, continue through PREPARING → EXTRACTING → VALIDATING → PUBLISHING and retain the immutable previous artifact chain for change detection.
4. Keep `NEEDS_REVIEW` terminal for human review; do not silently overwrite review state with a refresh.

### Required Interfaces and Contracts

Supported combinations:

| Existing state | Fetch result | Required behavior |
|---|---|---|
| PUBLISHED/SKIPPED_UNCHANGED | same checksum | persist `SKIPPED_UNCHANGED`; zero AI calls |
| PUBLISHED/SKIPPED_UNCHANGED | changed checksum | create RawArtifact version; run all downstream stages |
| NEEDS_REVIEW | any | return current row; explicit review action controls continuation |

### Error Handling and Logging

- Refresh fetch failures become `RETRYABLE`/`FAILED` with `resume_from=FETCHING` inferred from transition history and safe upstream error fields.
- Log `pipeline_id`, stable key prefix, artifact checksum prefix and stage; never raw body.

### Tests

- v1 publish → mutate fixture/source response to v2 → run same key → assert fetch twice, artifact version 2, AI twice, publish twice.
- v1 publish → same source again → assert `SKIPPED_UNCHANGED` and AI call count unchanged.

### Acceptance Criteria

- A published source is checked on every explicit pipeline run; the key remains stable and does not suppress refresh.

### Verification

- `pytest -q tests/integration/test_pipeline.py`.

## Task 8: Resume retryable failures

### Intent

Avoid repeating network, preparation and AI work after a later stage fails.

### Implementation Steps

1. When an exception moves a run to `RETRYABLE`, preserve the current stage in the transition history (`from` field) and keep persisted `artifact_id`/`extraction_id`.
2. On a later call with the same key and `RETRYABLE`/manual-retry `FAILED`, read the last transition into RETRYABLE/FAILED and transition back only to that stage: FETCHING, PREPARING, EXTRACTING, VALIDATING or PUBLISHING.
3. For PUBLISHING retry, call only `PublishingService.publish(extraction_id, correlation_id)`; candidate idempotency keys protect partial Core publishes.
4. For EXTRACTING retry, reuse the persisted artifact/prepared document. For VALIDATING/PUBLISHING retry, reuse persisted extraction/candidates. Never call `FetchService` unless the failed stage is FETCHING.
5. Bound attempts using `max_attempts`; once exhausted transition to `FAILED` and require an explicit operator decision to retry.

### Required Interfaces and Contracts

Supported combinations:

| Failure stage | Persisted prerequisite | Retry side effects |
|---|---|---|
| FETCHING | none | fetch only |
| PREPARING | artifact | storage read/preparation, no network |
| EXTRACTING | artifact + prepared | AI only, no network |
| VALIDATING | extraction/candidates | validation/Core ontology read only |
| PUBLISHING | validated extraction/candidates | Core publish only |

### Error Handling and Logging

- Use `DomainError.code/message` where available; unexpected errors become bounded `UNEXPECTED_ERROR`.
- Log `resumed_from`, `artifact_id`, `extraction_id`, attempt number and call suppression decisions at DEBUG; errors at ERROR with correlation ID.

### Tests

- Core outage after extraction: second run uses same extraction ID, fetch call count stays 1 and AI call count stays 1.
- AI failure after fetch/preparation: second run reuses artifact, fetch stays 1, AI becomes 2.
- Validate no retry crosses a terminal `NEEDS_REVIEW` without explicit handling.

### Acceptance Criteria

- Retry tests prove stage-local call counts, not just final state.

### Verification

- `pytest -q tests/integration/test_failure_boundaries.py tests/unit`.

## Task 9: Harden pipeline persistence and observability

### Intent

Make transition history, optimistic locking and logs sufficient to diagnose refresh/retry without storing document bodies in pipeline state.

### Implementation Steps

1. Confirm repository transitions commit after each durable stage and preserve `row_version` checks.
2. Include `resume_from`/stage details in transition history or a bounded error metadata field, while keeping existing migration compatibility.
3. Ensure pipeline payload contains IDs/references only; raw bytes remain in `ArtifactStoragePort` and extraction candidates remain normalized JSON rows.
4. Update pipeline docs and transition diagram.

### Error Handling and Logging

- Optimistic-lock conflicts are surfaced as `CONCURRENT_UPDATE` and do not overwrite another attempt.
- Logs must not contain prepared text, AI prompts, tokens or raw artifact bodies.

### Tests

- Repository integration test asserts every successful stage is visible after a new session and the pipeline row contains references, not body bytes.

### Acceptance Criteria

- A process restart after any committed stage can resume without reconstructing input from the network.

### Verification

- `pytest -q tests/integration/test_pipeline.py tests/integration/test_failure_boundaries.py`.

## Phase Risks and Mitigations

- Risk: partial publish leaves some candidates already accepted. Mitigation: stable per-candidate idempotency keys and persisted candidate Core IDs.
- Risk: refresh mutates a row currently being retried. Mitigation: optimistic row version and explicit terminal/retry state handling.
