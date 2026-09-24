# Phase 5: Regression, architecture gates and documentation

Plan: [index.md](index.md)
Tasks: 14-16
Depends on: Phase 1-4 / Tasks 1-13

## Objective

Prove the two repositories have one ingestion implementation, one HTTP integration seam, durable refresh/resume behavior and no accidental boundary regressions.

## Current-Code Evidence

| Path | Symbols / lines | Why it matters |
|---|---|---|
| `andromeda-ingestion-platform/tests/integration/test_pipeline.py` | current end-to-end fixture flows | Existing happy paths must be extended, not replaced. |
| `andromeda-ingestion-platform/tests/integration/test_failure_boundaries.py` | invalid AI/Core outage tests | Existing failure behavior is the starting point for stage-local retry assertions. |
| `andromeda-knowledge-core/tests/integration/test_acceptance.py` | source/observation/fact/rule acceptance | Canonical Core behavior must remain green after deleting ingestion code. |
| `.github/workflows/ci.yml` in both repositories | quality/migration jobs | Exact commands and empty PostgreSQL migration checks are completion evidence. |

## Files to Change

| Path | Action | Required change |
|---|---|---|
| Ingestion `tests/integration/test_pipeline.py`, `test_failure_boundaries.py` | modify | Refresh, unchanged, publish retry and extraction retry call-count tests. |
| Ingestion `tests/unit/test_discovery.py`, `test_preparation.py`, `test_ai_contract.py` | create | Focused adapter tests. |
| Core `tests/unit/test_architecture_boundary.py`, integration/API tests | create/modify | Forbidden imports, snapshot/source-document contracts and migrations. |
| Both repos `docs/*`, `README.md`, ADRs | modify | Final ownership, operations and limitations. |

## Task 14: Add Ingestion regression tests

### Intent

Turn every critical requirement into an executable regression rather than relying on final state only.

### Implementation Steps

1. Add a mutable fake fetcher/source or fixture switch that returns document v1 then v2 for the same source/item/profile key.
2. Assert refresh sequence: fetch v1 → publish; second same-body call → fetch again/`SKIPPED_UNCHANGED`/zero AI; changed body → new artifact version/new extraction/publish.
3. Add a Core outage adapter that fails on publish; assert retry uses the same artifact/extraction and does not call fetch/AI again.
4. Add an AI failure adapter after fetch; assert retry uses artifact/prepared data and calls AI only again.
5. Add contract tests for source-document registration, ontology request, evidence and HTTP security.

### Error Handling and Logging

- Tests should assert stable error codes and persisted state, not log text.
- Use deterministic call counters and fixtures; do not call the Internet.

### Acceptance Criteria

- All required refresh/retry combinations from the reconciliation table are covered.

### Verification

- `pytest -q` in Ingestion.

## Task 15: Add Core architecture and migration tests

### Intent

Make the ownership boundary fail closed if someone later reintroduces a fetcher, parser or LLM adapter in Core.

### Implementation Steps

1. Add an AST/source import test scanning `src/andromeda_core` for forbidden modules/symbols: Playwright, BeautifulSoup/bs4, pypdf/PDF parser, LLM SDKs, crawler/source-fetch adapters and raw HTTP client usage. Permit test-only `httpx` imports.
2. Add Core API tests for ontology snapshot and idempotent source-document registration.
3. Add migration verification from fresh head and from revision `0005`; assert canonical source/source-document tables remain and ingestion pipeline table is absent.
4. Ensure existing acceptance/negative/semantic tests continue to pass without mock document AI.

### Error Handling and Logging

- Architecture test failure must name file and forbidden import/symbol.
- Migration tests must surface the revision and table state; no destructive cleanup outside the temporary test database.

### Acceptance Criteria

- Core cannot silently acquire external ingestion dependencies without a failing test.

### Verification

- `pytest -q`, `ruff check src tests alembic scripts`, `mypy src`, `alembic check`, `alembic upgrade head`.

## Task 16: Finish documentation and quality gates

### Intent

Publish a truthful operating model and verify both repositories with reproducible commands.

### Implementation Steps

1. Update Ingestion docs for discovery, fetch security, artifact storage, preparation/evidence, AI ontology context, change detection, refresh and retry/resume.
2. Update Core docs/ADR to state that website changes and LLM provider changes are isolated to Ingestion.
3. Add a final architecture diagram/ownership table and explicitly label filesystem/mock Core/MockAI as development adapters; state S3-compatible storage and live AI as extension points if not implemented/tested.
4. Run exact CI commands for both repos and migration checks on empty PostgreSQL where Docker is available; capture commit/tree/status evidence.

### Error Handling and Logging

- Do not claim green CI, live provider behavior or production S3 support without command evidence.
- Keep secrets out of docs, fixtures and test payloads.

### Acceptance Criteria

- Documentation, source tree and test reports agree on one ingestion implementation and the Core seam.

### Verification

- `git diff --check` in both repositories.
- Exact workflow commands and Docker PostgreSQL migration checks.

## Phase Risks and Mitigations

- Risk: tests only pass with local uncommitted files. Mitigation: run from clean tracked tree/temporary databases and inspect `git status`.
- Risk: cross-repository commits drift. Mitigation: keep the same branch name, record both commit SHAs and run adapter tests against the actual Core route shape.
