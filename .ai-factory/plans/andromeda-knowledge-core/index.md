<!-- aif:plan-mode:ultra -->
# Ultra Implementation Plan: Andromeda Knowledge Core

Mode: ultra
Branch: none (the workspace is not a Git repository)
Created: 2026-09-24

## Original Request

The user requested, in Russian, a complete production-oriented Andromeda
Knowledge Core backend built from scratch: a modular-monolith semantic core
with versioned ontology, typed objects/relations, bi-temporal facts, sources,
observations, provenance, confidence, declarative rules and a safe typed Rule
DSL; deterministic Rule Engine; Derived Knowledge; dependency invalidation and
incremental recomputation; applicant contexts and overlays; change proposals,
human review, audit, AI/Jev ports, security boundaries, observability,
PostgreSQL/Alembic persistence, FastAPI/OpenAPI, Docker Compose, seed data,
automated tests, benchmark, CI, documentation, ADRs and Mermaid diagrams.
The acceptance scenarios include source-to-fact ingestion, rule lifecycle and
tests, evaluation, explainability, threshold replacement without business-code
changes, unknown ontology concepts, unresolvable conflicts and what-if
simulation. The complete original request is the user message that precedes
this plan; its wording is the authoritative behavioral specification.

## Settings

- Testing: yes
- Logging: verbose during development; safe structured INFO/DEBUG in runtime
- Docs: yes

## Requirements Reconciliation

Authority: the user specification in the current request is the primary
behavioral authority; no existing repository requirements were found.

| Decision / supported combination | Source path and section | Verification evidence |
|----------------------------------|-------------------------|-----------------------|
| PostgreSQL is the source of truth; graph is logical | User request §49-50 | Alembic schema, repository integration tests, ADR |
| Facts are separate from Derived Knowledge | §11, §25 | Fact/derived table tests and explain API |
| Rules are data and DSL is safe/no eval | §15-18 | DSL unit/property tests and threshold replacement |
| valid time and transaction time are distinct | §12 | Temporal repository tests |
| ingestion is Source → Observation → validation → Fact | §8-10, §33 | Scenario A and unknown-concept acceptance tests |
| activation requires validation/tests/conflict checks | §21 | Rule lifecycle integration tests |
| unresolved normative conflicts need review | §20, §55 | Conflict integration test |
| overlays do not mutate facts | §31-32, §56 | What-if scenario test |
| AI can propose but cannot activate truth | §35-36 | AI boundary/security tests |
| API is `/api/v1` and semantic routes are consumer-facing | §40-42, §74 | OpenAPI and route authorization tests |

## Architecture and Decisions

- Explicit Architecture in a modular monolith: pure domain + ports, application
  use cases, infrastructure adapters and FastAPI presentation adapters.
- PostgreSQL-backed normalized schema; JSON is limited to ASTs, metadata,
  extensible attributes, traces and snapshots.
- Async SQLAlchemy repositories; SQLite adapter is test-only.
- Domain IDs are application-generated strings to keep test adapter portable;
  production indexes and constraints are PostgreSQL-friendly.
- The Rule Engine is a pure deterministic module. Rule-specific policy arrives
  through AST/effect data and a generic effect registry.
- Activation is one transaction including supersession, audit and dependency
  invalidation. Optimistic versions prevent lost updates.
- Semantic API uses operation-oriented schemas and never exposes DB tables as a
  client contract.
- Local auth is an explicit `X-Role` seam documented for replacement by host
  authentication; semantic consumers cannot mutate normative data.

## Phase Index

1. [Phase 1: Foundation and Architecture](phase-01-foundation.md) — Tasks 1-3
2. [Phase 2: Persistence, Temporal Model and Provenance](phase-02-persistence.md) — Tasks 4-6
3. [Phase 3: Ontology and Knowledge Ingestion](phase-03-ontology-knowledge.md) — Tasks 7-9
4. [Phase 4: Rules as Data, Typed DSL and Lifecycle](phase-04-rules-dsl.md) — Tasks 10-13
5. [Phase 5: Rule Engine, Derived Knowledge and Explainability](phase-05-computation.md) — Tasks 14-16
6. [Phase 6: Dependency Graph and Incremental Recalculation](phase-06-dependencies.md) — Tasks 17-18
7. [Phase 7: Semantic API, Applicant Context and What-If Scenarios](phase-07-semantic-scenarios.md) — Tasks 19-20
8. [Phase 8: AI Ports, Security and Production Hardening](phase-08-hardening.md) — Tasks 21-23
9. [Phase 9: Demo, Acceptance Validation, Documentation and CI](phase-09-demo-docs-ci.md) — Tasks 24-27

## Cross-Phase Dependencies

- Tasks 1-3 provide the composition root and database seam for all later work.
- Tasks 4-6 provide migrations/repositories required by ontology and knowledge.
- Tasks 7-9 provide canonical facts/provenance consumed by rule tests and traces.
- Tasks 10-13 provide validated active rule data consumed by the engine.
- Tasks 14-18 provide materialized results, explanation and invalidation used by
  semantic operations.
- Tasks 19-23 expose and harden the stable client boundary.
- Tasks 24-27 package and verify the entire system.

## Tasks

### Phase 1: Foundation and Architecture

- [x] Task 1: Bootstrap application and dependency policy ([details](phase-01-foundation.md#task-1-bootstrap-the-application-and-dependency-policy))
- [x] Task 2: Add API errors, roles and observability ([details](phase-01-foundation.md#task-2-add-api-errors-roles-and-observability)) (depends on 1)
- [x] Task 3: Compose database session and health boundaries ([details](phase-01-foundation.md#task-3-compose-database-session-and-health-boundaries)) (depends on 1-2)

### Phase 2: Persistence, Temporal Model and Provenance

- [x] Task 4: Define normalized schema and migration ([details](phase-02-persistence.md#task-4-define-normalized-schema-and-migration)) (depends on 1-3)
- [x] Task 5: Implement temporal/provenance repository ports ([details](phase-02-persistence.md#task-5-implement-temporalprovenance-repository-ports)) (depends on 4)
- [x] Task 6: Add repository tests and migration checks ([details](phase-02-persistence.md#task-6-add-repository-tests-and-migration-checks)) (depends on 4-5)

### Phase 3: Ontology and Knowledge Ingestion

- [x] Task 7: Build versioned ontology and proposal workflow ([details](phase-03-ontology-knowledge.md#task-7-build-versioned-ontology-and-proposal-workflow)) (depends on 4-6)
- [x] Task 8: Implement source, observation, fact and relation flow ([details](phase-03-ontology-knowledge.md#task-8-implement-source-observation-fact-and-relation-flow)) (depends on 7)
- [x] Task 9: Add review queue, audit and admin knowledge endpoints ([details](phase-03-ontology-knowledge.md#task-9-add-review-queue-audit-and-admin-knowledge-endpoints)) (depends on 7-8)

### Phase 4: Rules as Data, Typed DSL and Lifecycle

- [x] Task 10: Define and validate typed Rule DSL ([details](phase-04-rules-dsl.md#task-10-define-and-validate-the-typed-rule-dsl)) (depends on 7-9)
- [x] Task 11: Implement effects, scope, exceptions and rule versions ([details](phase-04-rules-dsl.md#task-11-implement-effects-scope-exceptions-and-rule-versions)) (depends on 10)
- [x] Task 12: Add rule test cases and lifecycle operations ([details](phase-04-rules-dsl.md#task-12-add-rule-test-cases-and-lifecycle-operations)) (depends on 10-11)
- [x] Task 13: Implement deterministic rule conflict detection ([details](phase-04-rules-dsl.md#task-13-implement-deterministic-rule-conflict-detection)) (depends on 11-12)

### Phase 5: Rule Engine, Derived Knowledge and Explainability

- [x] Task 14: Implement pure Rule Engine ([details](phase-05-computation.md#task-14-implement-pure-rule-engine)) (depends on 10-13)
- [x] Task 15: Materialize Derived Knowledge and dependency metadata ([details](phase-05-computation.md#task-15-materialize-derived-knowledge-and-dependencies-metadata)) (depends on 14)
- [x] Task 16: Implement explainability chain ([details](phase-05-computation.md#task-16-implement-explainability-chain)) (depends on 15)

### Phase 6: Dependency Graph and Incremental Recalculation

- [x] Task 17: Implement dependency graph and invalidation ([details](phase-06-dependencies.md#task-17-implement-dependency-graph-and-invalidation)) (depends on 15-16)
- [x] Task 18: Add incremental recomputation instrumentation ([details](phase-06-dependencies.md#task-18-add-incremental-recomputation-instrumentation)) (depends on 17)

### Phase 7: Semantic API, Applicant Context and What-If Scenarios

- [x] Task 19: Implement applicant/query context and evaluate operations ([details](phase-07-semantic-scenarios.md#task-19-implement-applicantquery-context-and-evaluate-operations)) (depends on 14-18)
- [x] Task 20: Implement overlay simulation and comparisons ([details](phase-07-semantic-scenarios.md#task-20-implement-overlay-simulation-and-comparisons)) (depends on 19)

### Phase 8: AI Ports, Security and Production Hardening

- [x] Task 21: Add AI/Jev ports and mock adapters ([details](phase-08-hardening.md#task-21-add-aijev-ports-and-mock-adapters)) (depends on 8-9)
- [x] Task 22: Harden security and concurrency boundaries ([details](phase-08-hardening.md#task-22-harden-security-and-concurrency-boundaries)) (depends on 12-20)
- [x] Task 23: Add observability and operations documentation ([details](phase-08-hardening.md#task-23-add-observability-and-operations-documentation)) (depends on 2, 18, 22)

### Phase 9: Demo, Acceptance Validation, Documentation and CI

- [x] Task 24: Build deterministic/idempotent seed and CLI ([details](phase-09-demo-docs-ci.md#task-24-build-deterministicidempotent-seed-and-cli)) (depends on 7-20)
- [x] Task 25: Add Docker, migration path and CI ([details](phase-09-demo-docs-ci.md#task-25-add-docker-migration-path-and-ci)) (depends on 1-6)
- [x] Task 26: Complete documentation and ADRs ([details](phase-09-demo-docs-ci.md#task-26-complete-documentation-and-adrs)) (depends on 1-25)
- [x] Task 27: Run benchmark and all definition-of-done scenarios ([details](phase-09-demo-docs-ci.md#task-27-run-benchmark-and-all-definition-of-done-scenarios)) (depends on 24-26)

## Commit Plan

- Commit 1 after Tasks 1-6: `feat: establish Andromeda core foundation and persistence`
- Commit 2 after Tasks 7-13: `feat: add ontology ingestion and declarative rule lifecycle`
- Commit 3 after Tasks 14-20: `feat: add deterministic computation and semantic API`
- Commit 4 after Tasks 21-23: `feat: harden security AI boundaries and observability`
- Commit 5 after Tasks 24-27: `feat: ship demo operations documentation and acceptance suite`

## Definition of Done

- The application starts through Docker Compose after `alembic upgrade head`.
- Swagger `/docs` and OpenAPI `/openapi.json` expose documented admin and
  semantic contracts.
- Scenarios A-H have automated integration coverage and are manually runnable.
- Rule threshold replacement changes behavior through persisted rule data only.
- Unknown concepts and unresolvable conflicts enter review, never silently activate.
- Facts, derived values, temporal queries, provenance and dependency invalidation
  are separately represented and explainable.
- Tests, lint, type checks, migrations, benchmark and security boundary checks
  have been run; limitations are stated in README.

## Verification record

The final local verification recorded 13 passing pytest tests, clean Ruff and
Mypy checks, `alembic upgrade head` plus `alembic check` on SQLite, and the
same empty-schema migration plus seed on a local PostgreSQL 16 container.
The benchmark dataset declares 10 universities, 5,000 programs, 30,000 facts
and 1,000 rules. Docker Compose syntax was validated; the Compose image build
could not be completed in this environment because Docker Hub access through
the configured proxy was refused. The final PostgreSQL API smoke also returned
semantic score 305, provenance explanation, selector dependency edges and
healthy liveness/readiness responses.
