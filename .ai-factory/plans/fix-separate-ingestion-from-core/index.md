<!-- aif:plan-mode:ultra -->
# Ultra Implementation Plan: Separate Ingestion Ownership from Knowledge Core

Mode: ultra
Branch: fix/separate-ingestion-from-core (coordinated in both repositories)
Created: 2026-09-24

## Original Request

The complete user-provided specification is attached in `C:\CodexData\attachments\9d29490b-f53b-4f2b-9f62-7f9260c56e4a\Вставленный текст.txt` and requires moving all external-document ingestion ownership from `andromeda-knowledge-core` to `andromeda-ingestion-platform`, preserving refresh/resume, ontology-aware AI extraction, SSRF-safe fetch/discovery, evidence locators, typed Core HTTP contracts, regression tests and documentation.

## Settings

- Testing: yes
- Logging: verbose during implementation; production-safe structured fields only
- Docs: yes

## Requirements Reconciliation

Authority: the attached user specification is the governing architecture and behavior source; current `main` code and ADRs provide compatibility constraints.

| Decision / supported combination | Source path and section | Verification evidence |
|---|---|---|
| Core never fetches or interprets external documents and never calls document-extraction AI | attached specification sections 2, 3, 18 | Core import-boundary test, source scan, Core test suite |
| Ingestion is the only discovery/fetch/artifact/preparation/extraction/validation/publish orchestrator | attached sections 6, 9, 11, 17 | ingestion pipeline tests and architecture docs |
| A terminal run re-fetches; equal checksum is `SKIPPED_UNCHANGED`, changed checksum creates a new artifact path | attached section 6, Refresh | refresh regression test with v1/v2 and unchanged replay |
| Retry resumes from persisted artifact/extraction and does not repeat earlier successful stages | attached section 6, Retry / Resume | publish retry and extraction retry tests with call counters |
| AI receives object types, properties, relations, ontology version and Rule DSL schema | attached sections 5 and 8 | HTTP AI request contract test |
| Raw bytes remain behind `ArtifactStoragePort`, never in Core | attached section 7 | storage/repository model inspection and architecture test |
| Core integration uses only versioned HTTP DTOs through `KnowledgeCorePort`/adapter | attached sections 4, 12, 13 | Core API contract tests and adapter MockTransport tests |
| SSRF, redirects, body/status handling, sitemap and same-origin HTML discovery are bounded | attached sections 9 and 14 | security and discovery tests |

## Architecture and Decisions

- `andromeda-knowledge-core` keeps ontology, objects, relations, observations, sources/source-document metadata, provenance/evidence, rules, reviews, audit, derived knowledge, dependency graph and Semantic API.
- `andromeda-ingestion-platform` owns source registry, discovery, byte fetch, immutable artifact metadata/storage, preparation, evidence locators, AI extraction, candidate validation, change detection, retry/resume and publishing.
- The Core HTTP seam is the only cross-repository integration. Ingestion does not import Core ORM/models or share a database.
- Core exposes `GET /api/v1/ontology/snapshot` and `POST /api/v1/source-documents` because the existing routes do not provide the full extraction contract or a typed source-document registration operation.
- Existing generic `POST /api/v1/observations` remains the publish endpoint; candidate kind and evidence stay in typed fields/raw payload until dedicated candidate routes are justified.
- Core's existing `0005_ingestion_pipeline` migration is preserved for history and followed by a forward `0006` removal migration; no ingestion table/model remains in the current ORM.
- Ingestion keeps one stable stream idempotency key and reuses a pipeline row for a new checksum after a terminal refresh, while persisted transition history and artifact versions preserve auditability. Retry stage is inferred from the persisted transition immediately preceding `RETRYABLE`, avoiding a second pipeline table in Core.

## Phase Index

1. [Phase 1: Core ownership cleanup and compatibility migration](phase-01-core-cleanup.md) — Tasks 1-3
2. [Phase 2: Versioned Core contract and anti-corruption adapter](phase-02-core-contract.md) — Tasks 4-6
3. [Phase 3: Refreshable and resumable Ingestion pipeline](phase-03-pipeline.md) — Tasks 7-9
4. [Phase 4: Secure discovery, preparation, evidence and AI](phase-04-ingestion-adapters.md) — Tasks 10-13
5. [Phase 5: Regression, architecture gates and documentation](phase-05-verification-docs.md) — Tasks 14-16

## Cross-Phase Dependencies

- Tasks 4-6 depend on Task 1 because Core routes and repositories must be free of ingestion orchestration before the HTTP seam is finalized.
- Tasks 7-9 depend on Tasks 4-6 because publishing and ontology retrieval must use the typed Core port.
- Tasks 10-13 depend on Task 7 for stage boundaries and on Task 4 for ontology-aware extraction context.
- Tasks 14-16 depend on every prior task because they verify both repositories, migrations, contracts and architecture imports together.

## Tasks

### Phase 1: Core ownership cleanup and compatibility migration

- [x] Task 1: Remove Core-side external ingestion orchestration and adapters ([details](phase-01-core-cleanup.md#task-1-remove-core-side-external-ingestion))
- [x] Task 2: Remove Core ingestion persistence from the active ORM and add a safe forward migration ([details](phase-01-core-cleanup.md#task-2-remove-core-ingestion-persistence))
- [x] Task 3: Rewrite Core architecture/AI/ingestion documentation and dependency ownership ([details](phase-01-core-cleanup.md#task-3-rewrite-core-architecture-documentation))

### Phase 2: Versioned Core contract and anti-corruption adapter

- [x] Task 4: Add the ontology snapshot endpoint with Rule DSL schema ([details](phase-02-core-contract.md#task-4-add-ontology-snapshot-contract))
- [x] Task 5: Add source-document registration and preserve observation idempotency ([details](phase-02-core-contract.md#task-5-add-source-document-registration))
- [x] Task 6: Adapt the Ingestion `KnowledgeCorePort` HTTP adapter and mock to the Core contracts ([details](phase-02-core-contract.md#task-6-adapt-the-ingestion-core-port))

### Phase 3: Refreshable and resumable Ingestion pipeline

- [x] Task 7: Make terminal runs re-fetch and distinguish unchanged from changed artifacts ([details](phase-03-pipeline.md#task-7-make-terminal-runs-refreshable))
- [x] Task 8: Resume retryable failures from the last persisted successful stage ([details](phase-03-pipeline.md#task-8-resume-retryable-failures))
- [x] Task 9: Preserve durable state and observability for refresh/retry semantics ([details](phase-03-pipeline.md#task-9-harden-pipeline-persistence-and-observability))

### Phase 4: Secure discovery, preparation, evidence and AI

- [x] Task 10: Strengthen HTTP fetch SSRF/status/redirect/body protections ([details](phase-04-ingestion-adapters.md#task-10-strengthen-http-fetching))
- [x] Task 11: Implement bounded sitemap and same-origin HTML link discovery ([details](phase-04-ingestion-adapters.md#task-11-implement-configured-discovery))
- [x] Task 12: Improve HTML/PDF/text evidence locators and immutable artifact references ([details](phase-04-ingestion-adapters.md#task-12-improve-evidence-locators))
- [x] Task 13: Pass the complete ontology snapshot and Rule DSL schema to structured AI ([details](phase-04-ingestion-adapters.md#task-13-pass-ontology-to-structured-ai))

### Phase 5: Regression, architecture gates and documentation

- [x] Task 14: Add refresh/retry/ontology/SSRF/discovery regression tests in Ingestion ([details](phase-05-verification-docs.md#task-14-add-ingestion-regression-tests))
- [x] Task 15: Add Core import-boundary and HTTP contract tests plus migration checks ([details](phase-05-verification-docs.md#task-15-add-core-architecture-and-migration-tests))
- [x] Task 16: Update both repositories' operational and architecture documentation and run all quality gates ([details](phase-05-verification-docs.md#task-16-finish-documentation-and-quality-gates))

## Commit Plan

- **Commit 1** (Tasks 1-3): `refactor(core): remove external ingestion ownership`
- **Commit 2** (Tasks 4-6): `feat(contract): expose ontology and source document boundaries`
- **Commit 3** (Tasks 7-9): `fix(ingestion): refresh sources and resume persisted stages`
- **Commit 4** (Tasks 10-13): `fix(ingestion): harden discovery fetch and extraction adapters`
- **Commit 5** (Tasks 14-16): `test: enforce the core and ingestion architecture boundary`

## Definition of Done

- Core contains no external fetch, crawl, discovery, raw-byte, document-preparation or LLM extraction implementation/import.
- Ingestion has one orchestration path with refresh and stage-local retry/resume.
- Core contract exposes ontology snapshot and source-document metadata; publishing uses only `KnowledgeCorePort`.
- Raw artifacts are stored through `ArtifactStoragePort`; Core stores only metadata/provenance/evidence references.
- Both repositories pass tests, Ruff, mypy and empty-PostgreSQL migration checks where available.
- Documentation and final report explicitly state what was verified, what remains mock, and which storage/provider integrations remain extension points.
