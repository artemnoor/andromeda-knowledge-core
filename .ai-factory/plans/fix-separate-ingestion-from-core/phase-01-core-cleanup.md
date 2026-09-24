# Phase 1: Core ownership cleanup and compatibility migration

Plan: [index.md](index.md)
Tasks: 1-3
Depends on: none

## Objective

Make Knowledge Core a semantic/provenance backend only while preserving the existing canonical knowledge model and keeping migration history upgradeable.

## Current-Code Evidence

| Path | Symbols / lines | Why it matters |
|---|---|---|
| `src/andromeda_core/application/ingestion_pipeline.py` | `IngestionPipelineService` | Entire external fetch/extract/publish orchestration to delete from Core. |
| `src/andromeda_core/infrastructure/adapters/` | HTTP, discovery, evidence and structured AI adapters | External-document implementations currently violate the Core seam. |
| `src/andromeda_core/infrastructure/db/models.py` | `IngestionPipelineModel` / `ingestion_pipeline_runs` | Core-only persistence of raw bytes and extraction must disappear from active ORM. |
| `alembic/versions/0005_ingestion_pipeline.py` | upgrade creating `ingestion_pipeline_runs` | Already part of migration history; remove with a forward migration rather than rewriting applied history. |
| `src/andromeda_core/domain/ports/ai.py`, `sources.py` | document/source adapter ports | No current Core application consumer; remove extraction/fetch seams and retain only API candidate contracts. |

## Files to Change

| Path | Action | Required change |
|---|---|---|
| `src/andromeda_core/application/ingestion_pipeline.py` | delete | Remove pipeline orchestration. |
| `src/andromeda_core/domain/ports/ingestion.py`, `ai.py`, `sources.py` | delete or reduce | Remove external ingestion ports; keep no document-fetch/LLM implementation in Core. |
| `src/andromeda_core/infrastructure/adapters/*` | delete | Delete HTTP source, discovery, evidence, mock source/AI and structured JSON extraction adapters. |
| `src/andromeda_core/infrastructure/db/models.py`, `repositories.py`, `domain/ports/repositories.py` | modify | Remove pipeline model/import/methods only; keep Source, SourceDocument, Observation, Provenance and all canonical models. |
| `alembic/versions/0006_remove_ingestion_pipeline.py` | create | Drop `ingestion_pipeline_runs` and indexes after `0005`, with a reversible downgrade that recreates its schema if practical. |
| `tests/unit/test_ingestion_pipeline.py`, ingestion persistence test section | delete/modify | Move behavioral coverage to Ingestion repository; Core tests must cover only API/provenance behavior. |

## Task 1: Remove Core-side external ingestion

### Intent

Delete all Core implementations whose behavior depends on external URLs, source crawling, document bytes, HTML/PDF parsing or LLM calls. Do not delete Core's source metadata, source-document metadata, observations, provenance or candidate acceptance logic.

### Implementation Steps

1. Delete `application/ingestion_pipeline.py`, `domain/ports/ingestion.py`, source/fetch/discovery/evidence/structured-AI adapters and their unit tests.
2. Remove the ingestion-only additions from `domain/ports/ai.py`; if no remaining Core code imports the file, delete the file and `tests/unit/test_ai_boundary.py`. Keep `ObservationCreate` and proposal/review application behavior because candidates enter through HTTP.
3. Remove any runtime `httpx` dependency from Core; keep it in `[dev]` only if the test transport imports it. Verify no production `src/andromeda_core` import mentions `httpx`, `bs4`, `pypdf`, `playwright`, an LLM SDK or crawler/fetch adapter.
4. Remove stale package exports and grep all source/tests/docs for deleted symbols.

### Required Interfaces and Contracts

- Core inbound candidates remain `POST /api/v1/observations` with strict `ObservationCreate`.
- No Core application service may accept a URL and perform I/O; source URLs are metadata only.
- Core may store an evidence locator received in an observation/provenance payload but never constructs one from bytes.

### Error Handling and Logging

- Deletion must not replace removed behavior with silent fallbacks.
- Existing Core API errors, correlation IDs and structured logging remain unchanged.
- Do not log raw document bodies, prompts or credentials anywhere in Core.

### Tests

- Add/retain an import-boundary test in Task 15.
- Run `python -m pytest -q`, `ruff check src tests alembic scripts`, and `mypy src` after deletion.

### Acceptance Criteria

- `rg` finds no external fetch/discovery/evidence/structured-document-AI implementation under `src/andromeda_core`.
- Existing acceptance tests for ontology, source metadata, observations, facts, relations, rules, review, derived knowledge and Semantic API still pass.

### Verification

- `rg -n "BeautifulSoup|pypdf|playwright|StructuredJson|HttpSourceFetcher|IngestionPipelineService|ingestion_pipeline" src`
- Expected result: no matches except deliberate migration-history/doc references handled in later tasks.

## Task 2: Remove Core ingestion persistence

### Intent

Ensure the active Core schema contains no raw fetched content or pipeline-run state while preserving upgrade safety for environments that already applied `0005`.

### Implementation Steps

1. Remove `IngestionPipelineModel` from `models.py`, its repository import and `find_latest_pipeline`, `find_pipeline_by_checksum`, `create_pipeline`, `update_pipeline` methods, and the four repository-port methods.
2. Create `0006_remove_ingestion_pipeline.py` after `0005`, dropping `ingestion_pipeline_runs` and its named indexes/constraints. Keep `0005` immutable as migration history; document that `0006` is the forward cleanup.
3. Ensure `Base.metadata` still includes Source/SourceDocument/Observation/Provenance and all other canonical models.
4. Run fresh and upgrade-from-`0005` SQLite migrations; run empty PostgreSQL migration in CI/Docker when available.

### Required Interfaces and Contracts

- Core's `sources` and `source_documents` tables remain allowed metadata/provenance records.
- No column in Core models may be a raw fetched body or extraction result cache.

### Error Handling and Logging

- Migration must fail loudly on unexpected schema errors; do not catch/drop arbitrary tables.
- Downgrade should be explicit and limited to the removed table if the repository's migration policy requires reversible migrations.

### Tests

- Add a migration test that upgrades through `0005` then `0006` and asserts `ingestion_pipeline_runs` is absent while `sources` and `source_documents` remain.
- Run `alembic upgrade head` and `alembic check` on SQLite; run PostgreSQL upgrade in the repository CI.

### Acceptance Criteria

- ORM import succeeds without `IngestionPipelineModel`.
- Current head has no Core table for fetched bytes or ingestion pipeline runs.

### Verification

- `alembic upgrade head` on a fresh DB and a DB upgraded through `0005`.
- Expected result: both finish at `0006`; only canonical Core tables remain.

## Task 3: Rewrite Core architecture documentation

### Intent

Make the ownership rule visible to maintainers and future agents so a changed university website or LLM provider never requires Core changes.

### Implementation Steps

1. Rewrite `README.md`, `docs/architecture.md`, `docs/ingestion.md` and `docs/ai-boundaries.md` to say Core never fetches/interprets external documents and only accepts typed candidates/metadata over HTTP.
2. Update `.ai-factory/DESCRIPTION.md` and `.ai-factory/ARCHITECTURE.md` to remove Core source/AI adapter claims and add the Ingestion Platform integration seam.
3. Keep API group documentation for `/sources`, `/source-documents`, `/observations`, provenance and ontology snapshot accurate.

### Error Handling and Logging

- Documentation must not claim live AI, S3 or external ingestion is implemented unless a test/command proves it.
- Mark mock Core adapters and optional provider/storage implementations explicitly.

### Tests

- Documentation grep in Task 16 must fail on statements that Core downloads or parses external documents.

### Acceptance Criteria

- A maintainer can identify Core's allowed ownership and the external service's ownership without reading code.

### Verification

- `rg -n "Core.*(fetch|download|crawl|LLM|PDF)|fetch.*inside.*Core" README.md docs .ai-factory`
- Expected result: only negative statements such as “Core never fetches” remain.

## Phase Risks and Mitigations

- Risk: deleting generic AI ports breaks hidden imports. Mitigation: grep all repository code before deletion and replace only actual API contracts, not canonical proposal/review logic.
- Risk: migration `0006` is not portable. Mitigation: test SQLite fresh/upgrade paths and PostgreSQL in CI before claiming completion.
