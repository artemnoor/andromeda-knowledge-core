# Andromeda Knowledge Core

Andromeda Knowledge Core is a modular-monolith semantic backend for a
versioned education knowledge graph. PostgreSQL is the source of truth; the
graph is represented by typed objects, first-class relations, facts, rules and
dependency edges rather than by a separate graph database.

The core boundary is a stable Semantic API. Future Andromeda backend, Web, MAX
and assistant clients do not need to know the database schema.

## Run locally

Requirements: Docker Desktop and Docker Compose.

~~~powershell
Copy-Item .env.example .env
docker compose up --build
~~~

The API container runs alembic upgrade head before Uvicorn. Then load the
repeatable demo dataset:

~~~powershell
docker compose exec api python -m scripts.seed_demo
~~~

Open [Swagger UI](http://localhost:8000/docs), [OpenAPI](http://localhost:8000/openapi.json),
[liveness](http://localhost:8000/health) or [readiness](http://localhost:8000/ready).

For a dependency-free test run, the repository supports SQLite through the
async test adapter:

~~~powershell
$env:PYTHONPATH = "src;."
pytest -q
ruff check src tests alembic scripts
mypy src
~~~

## Architecture

~~~mermaid
flowchart LR
  Client[Future clients] --> Semantic[Semantic API /api/v1/semantic]
  Admin[Controlled admin/review clients] --> AdminAPI[Admin API /api/v1]
  Semantic --> App[Application use cases]
  AdminAPI --> App
  App --> Domain[Pure domain: ontology, DSL, engine, graph]
  App --> Ports[Ports: repositories]
  Ports --> PG[(PostgreSQL)]
  Ports --> Adapters[SQLAlchemy and optional adapters]
  Domain --> Derived[Derived knowledge + traces]
  Derived --> PG
~~~

The code is split into 'domain', 'application', 'infrastructure' and
'presentation'. FastAPI routes validate and serialize only; business behavior
lives in application services and the pure engine. SQLAlchemy models stay in
the infrastructure adapter.

## Main API groups

| Group | Examples | Access |
|---|---|---|
| /api/v1/ontology | versions, definitions, proposals | reader for reads; editor/reviewer for mutations |
| /api/v1/objects, /facts, /relations | typed knowledge graph data | editor for mutations |
| /api/v1/sources, /source-documents, /observations | external ingestion contract | editor/reviewer |
| /api/v1/rules | create, validate, test, activate | editor; reviewer for activation |
| /api/v1/derived | materialized values and dependencies | reader; admin for manual invalidation |
| /api/v1/reviews | approve, reject, modify | reviewer |
| /api/v1/changes, /audit | classified changes and audit events | reviewer |
| /api/v1/semantic | evaluate, simulate, explain, program projections | reader |

The local identity seam uses X-Role: EDITOR, X-Role: REVIEWER or X-Role: ADMIN.
Without a header, read operations are READER; mutation operations are denied.
This is deliberately a replaceable local boundary, not a claim to provide
production authentication. The host Andromeda backend must resolve its
authenticated principal and inject the role before deployment.

All errors use:

~~~json
{"error":{"code":"RULE_CONFLICT","message":"...","details":{},"trace_id":"..."}}
~~~

Pass X-Correlation-ID to correlate HTTP logs, rule execution and audit data.

## End-to-end example

1. Register a source with POST /api/v1/sources.
2. Submit a source assertion to POST /api/v1/observations.
3. Promote it with POST /api/v1/observations/{id}/accept.
4. Create a draft rule with an AST condition and declarative effects.
5. Call /rules/{id}/validate, /test, then /activate with reviewer role.
6. Call POST /api/v1/semantic/evaluate with applicant/query context.
7. Follow the returned result_id through GET /api/v1/semantic/explain/{result_id}.

The seeded demonstration contains a base-score rule and the data-only rule
admission.additional_exam_bonus: an additional physics exam with score >=90
adds 30. Creating version 2 with >=85, setting replaces_rule_id, and
activating it invalidates dependent derived values. No engine/application code
changes.

What-if uses the same engine and an in-memory overlay:

~~~json
{
  "base_context": {
    "applicant": {"scores": {"physics": 84}, "additional_exams": [{"code": "physics"}]},
    "context": {"program_id": "<program-id>", "campaign_year": 2027, "base_score": 275},
    "persist": false
  },
  "overrides": [{"property": "scores.physics", "value": 94}]
}
~~~

## Rule DSL and truth boundaries

Rules are JSON AST data, never Python code. The closed DSL supports logical
operators, comparisons, membership, exists/not_exists, count/sum/min/max, and
any/all/none/at_least. References can target canonical facts, relations,
query context and applicant context. Effects are registered generic handlers
(SET, ADD, SUBTRACT, GRANT, DENY, eligibility markers and EMIT_DERIVED). No
eval, imports or arbitrary code are involved.

The separate Andromeda Ingestion Platform discovers and fetches external
documents, stores raw artifacts, runs extraction adapters and sends
evidence-backed observations through the Core API. Core does not fetch, parse,
call AI providers or store raw bytes. It cannot activate rules, mutate ontology
or overwrite verified facts from an incoming observation without the configured
review policy. Unknown concepts create an ontology change proposal and review
item. Equal-priority contradictory rules create RULE_CONFLICT and remain
inactive.

## Persistence and operations

Alembic migrations are the only production schema path. The application never
calls create_all() at startup. The normalized schema includes ontology
versions, object types, property/relation definitions, sources/documents,
observations, provenance, typed facts, relations, rules/tests, rule relations,
derived values, dependencies, reviews, audit and change events.

Facts, relations and rules carry valid time and transaction time. A temporal
query can ask what was valid at a world-time instant and what Andromeda knew at
a transaction-time instant. Derived rows are rebuildable projections and are
never used as canonical facts.

Operational endpoints are /health, /ready and /metrics (the latter is omitted
from the public OpenAPI schema). Logs are JSON
lines without request bodies or secrets. Request size, CORS and security
headers are configurable through environment settings.

## Benchmarks

Run the deterministic synthetic benchmark:

~~~powershell
$env:PYTHONPATH = "src;."
python benchmarks/benchmark_engine.py
~~~

It reports median and p95 timings for semantic rule evaluation, dependency
lookup and targeted invalidation on a declared synthetic dataset. Benchmark
numbers are environment-dependent and are not used as correctness gates.

## Documentation

- Architecture: docs/architecture.md
- Ontology and evolution: docs/ontology.md
- Rule DSL: docs/rule-dsl.md
- Bi-temporal model: docs/temporal-model.md
- Provenance: docs/provenance.md
- Dependency graph: docs/dependency-graph.md
- Ingestion: docs/ingestion.md
- Semantic API: docs/semantic-api.md
- AI boundaries: docs/ai-boundaries.md
- Operations and observability: docs/observability.md
- Security: docs/security.md
- ADRs: docs/adr/

## Deliberate limits

The first release is a modular monolith. Redis, background workers, external
AI credentials, full-text search, program comparison ranking and distributed
event delivery are extension points rather than Core runtime dependencies.
SQLite
is a test adapter; production deployment is PostgreSQL. The local X-Role
header must be replaced by the host authentication boundary before exposing
admin routes to untrusted networks.
