# Phase 9: Demo, Acceptance Validation, Documentation and CI

Plan: [index.md](index.md)
Tasks: 24-27
Depends on: Phase 8 / Tasks 21-23

## Objective

Deliver a runnable repository with Docker Compose, repeatable demo data,
acceptance scenarios, benchmark evidence, Mermaid documentation, ADRs and CI.

## Files to Change

| Path | Action | Required change |
|------|--------|-----------------|
| `scripts/seed_demo.py` | create | Idempotent BMSTU/demo ontology, sources, facts and rules. |
| `Dockerfile` | create | Production-oriented image. |
| `docker-compose.yml` | create | PostgreSQL, migration and API services. |
| `README.md` | create | Setup, API walkthrough and integration contract. |
| `docs/*.md` | create | Architecture, ontology, DSL, temporal, provenance, dependencies, ingestion, semantic API and AI boundary. |
| `docs/adr/*.md` | create | Required architecture decisions. |
| `benchmarks/benchmark_engine.py` | create | Synthetic benchmark for query/evaluation/invalidation. |
| `.github/workflows/ci.yml` | create | Ruff, mypy, tests, migration check and Docker smoke. |
| `tests/acceptance/test_definition_of_done.py` | create | All scenarios A-H and threshold replacement. |

## Task 24: Build deterministic/idempotent seed and CLI

### Intent

Give developers a complete demo that proves the engine is generic and the API
can be exercised from Swagger.

### Implementation Steps

1. Seed ontology version with University, Program, Exam, Subject, Campaign,
   Benefit and relevant properties/relations.
2. Seed BMSTU, two programs, exams, source PDF metadata, observation and
   accepted facts with evidence locator.
3. Seed active rule v1 (`fourth_exam_score >= 90 → ADD admission_score 30`) and
   at-least-2-of-3 benefit rule with tests.
4. Make seed safe to repeat through natural keys/checksums/upserts.
5. Provide `python -m scripts.seed_demo` and development-only `POST /seed/demo`
   guarded by environment/role.

### Required Interfaces and Contracts

The threshold is present only in seed rule JSON; no Python engine branch names
the threshold or BMSTU. Seed reports created/reused IDs and does not duplicate
facts/rules.

### Error Handling and Logging

Seed runs in a transaction and rolls back on failure. Log counts and IDs, not
full payloads.

### Tests

- Seed twice yields stable counts and IDs.
- Seeded evaluation and explain result succeed.

### Acceptance Criteria

After `docker compose up --build` and seed, `/docs` exposes a usable end-to-end
demo.

### Verification

- `python -m scripts.seed_demo`
- `pytest -q tests/acceptance/test_definition_of_done.py -k seed`

## Task 25: Add Docker, migration path and CI

### Intent

Make empty DB → migrations → running API repeatable locally and in CI.

### Implementation Steps

1. Add multi-stage-ish Dockerfile with non-root runtime, health command and
   `uvicorn` entrypoint.
2. Add Compose PostgreSQL service with persistent volume, healthcheck and API
   command that runs `alembic upgrade head` then starts Uvicorn.
3. Add CI workflow for Ruff, mypy, pytest, `alembic check` and a PostgreSQL
   migration smoke job.
4. Document external AI credentials are optional and mocks are used in CI.

### Required Interfaces and Contracts

- No schema creation in app startup.
- `.env.example` and Compose defaults contain no secrets.
- `/health`, `/ready`, `/docs` are the documented URLs.

### Error Handling and Logging

Container migration failure stops API startup and is visible in logs; readiness
does not report success before schema is migrated.

### Tests

- Build image and run migrations on empty database.
- API health/readiness smoke against Compose.

### Acceptance Criteria

Clean local development path works from an empty DB.

### Verification

- `docker compose up --build -d`
- `docker compose exec api alembic current`
- `docker compose down`

## Task 26: Complete documentation and ADRs

### Intent

Make architecture understandable without reading all source code and explain
future integration boundaries.

### Implementation Steps

1. Write README with endpoint map, seed commands, Swagger walkthrough,
   integration examples, roles, limitations and known technical debt.
2. Add Mermaid diagrams for overall architecture, ingestion pipeline, lifecycle,
   ontology evolution, dependency recalculation and semantic flow.
3. Add required ADRs: PostgreSQL over Neo4j initially, rules as data, custom
   DSL, Fact/Derived separation, bi-temporal model, modular monolith and AI
   activation boundary.

### Required Interfaces and Contracts

Docs reflect actual endpoint paths and tested payloads; unsupported external AI
integration is clearly marked as mock-only.

### Error Handling and Logging

Operational docs identify error codes, correlation IDs and non-secret logging.

### Tests

- Link/path smoke check for documented local files/endpoints.
- README examples are exercised by acceptance tests or marked conceptual.

### Acceptance Criteria

The final handoff can answer architecture/schema/API/DSL/temporal/provenance/
dependency/security/benchmark/limitations questions with repository evidence.

### Verification

- `rg -n "TODO|FIXME|placeholder|not implemented" src docs README.md`
- Expected result: no unfinished implementation markers.

## Task 27: Run benchmark and all definition-of-done scenarios

### Intent

Prove the architecture against the requested scenarios, including changing a
threshold only through data.

### Implementation Steps

1. Run API acceptance tests for scenarios A-H.
2. Create rule v2 with threshold 85 through API/fixture data, activate it and
   re-evaluate the same applicant; do not edit engine/application code.
3. Run synthetic benchmark with 10 universities, 5,000 programs, tens of
   thousands of facts and thousands of rules; record representative timings.
4. Run final static quality/security/migration checks and capture limitations.

### Required Interfaces and Contracts

Benchmark reports median/p95 or equivalent for semantic query, rule evaluation,
dependency lookup and incremental invalidation, with dataset and environment.

### Error Handling and Logging

Acceptance failure stops the release report; benchmark failures are warnings
only if functional tests pass and are documented as environment-limited.

### Tests

- A through H automated integration tests.
- Property-based deterministic/overlay/reproducibility invariants.
- Negative tests for all required invalid paths.

### Acceptance Criteria

The final test suite demonstrates that changing `>=90` to `>=85` changes the
result while Python business logic remains unchanged and all explanation,
review, conflict and what-if paths work.

### Verification

- `pytest -q`
- `python benchmarks/benchmark_engine.py`
- `ruff check src tests`
- `mypy src`

## Phase Risks and Mitigations

- Risk: benchmark is too large for CI. Mitigation: provide a deterministic
  scaled profile and report full profile locally; correctness remains mandatory.
- Risk: docs drift from routes. Mitigation: OpenAPI smoke and endpoint examples
  are part of acceptance tests.

## Phase Completion Checklist

- Tasks 24-27 pass acceptance, CI-quality and documentation checks.
- `index.md` task statuses are updated to complete.
