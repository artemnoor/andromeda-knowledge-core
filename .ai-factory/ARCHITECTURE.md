# Architecture: Explicit Modular Monolith

## Overview

Andromeda Knowledge Core uses Explicit Architecture inside a modular monolith.
The domain is the stable center: ontology semantics, temporal knowledge,
provenance, Rule DSL evaluation and dependency invalidation do not import
FastAPI, SQLAlchemy, PostgreSQL or an AI provider. Application modules expose
use cases through small interfaces. Infrastructure adapters implement ports,
and presentation adapters translate HTTP requests into application commands.

This shape keeps the first deployment operationally simple while preserving
seams for a later job worker, cache or independently deployed computation
component. The graph is a logical domain model persisted by PostgreSQL; no
graph database is required for the initial system.

## Folder Structure

```text
src/andromeda_core/
├── domain/
│   ├── common.py                 # IDs, temporal/provenance value objects
│   ├── ontology.py               # ontology entities and invariants
│   ├── knowledge.py              # objects, facts, relations, observations
│   ├── rules.py                  # rule lifecycle and conflict contracts
│   ├── derived.py                # derived values, traces and dependencies
│   ├── review.py                 # human review contracts
│   ├── dsl/                      # typed serializable Rule DSL
│   └── ports/                    # repository interfaces
├── application/                  # use-case orchestration
├── infrastructure/
│   ├── config.py                 # validated settings
│   ├── db/                       # SQLAlchemy models/session/repositories
│   ├── observability/            # JSON logs, correlation IDs, metrics
├── presentation/api/
│   ├── admin/                    # ontology, knowledge, rule and review routes
│   └── semantic/                 # stable consumer-facing routes
└── main.py                       # composition root
alembic/                          # migration scripts only
tests/                            # domain, integration and acceptance tests
docs/                             # architecture and operational documentation
```

## Dependency Rules

Dependencies point inward:

```text
FastAPI presentation → application use cases → domain interfaces/domain logic
PostgreSQL adapters ────────────────────────→ domain interfaces
Composition root ──────────────────────────→ all concrete adapters
```

- Domain modules must not import FastAPI, SQLAlchemy, settings or logging.
- Routes validate/serialize and call one application service; they do not issue SQL.
- Application services orchestrate and enforce policies; they do not parse HTTP.
- SQLAlchemy repositories implement ports and map persistence rows to domain DTOs.
- Cross-module access uses a public application/port interface, never private internals.
- External ingestion and AI extraction are outside this repository. Core accepts
  only source metadata and untrusted observation proposals over its API; they
  cannot activate ontology/rule changes without the Core review policy.

## Cross-repository ownership boundary

Andromeda Ingestion Platform owns discovery, HTTP/browser/file fetchers, raw
artifact bytes, preparation, extraction profiles, AI adapters, candidate
validation and refresh/retry orchestration. Knowledge Core owns ontology,
canonical objects, observations, provenance, facts, relations, rules, review,
audit and semantic evaluation. No shared ORM model or direct database access is
allowed between the repositories. A changed website or model provider should
be implemented in Ingestion without a Core code change.

## Module Boundaries

- `ontology`: versioned semantic types, constraints and change proposals.
- `knowledge`: objects, relations, sources, observations and accepted facts.
- `rules`: rule versions, DSL validation, rule tests and conflict policy.
- `rule_engine`: deterministic pure evaluation and explanation traces.
- `derived`: materialized derived knowledge and dependency graph operations.
- `semantic`: stable client-oriented read/evaluate/simulate/explain operations.
- `review`/`audit`: human decisions and append-only operational history.

The Rule Engine receives facts, relations, context, ontology metadata and active
rule data. It has no university-specific methods and no knowledge of admission
years or named exams.

## Persistence Strategy

PostgreSQL is the source of truth. Critical fields are normal columns with
foreign keys, temporal columns, status checks and targeted indexes. JSONB is
used only for Rule DSL ASTs, evidence/source metadata, extensible attributes,
execution traces and context snapshots. Migrations are the production schema
mechanism; application startup never calls `create_all()`.

SQLite is used only by fast tests through the same repository interfaces. The
production DSN is PostgreSQL/asyncpg and Docker runs `alembic upgrade head`
before starting the API.

## Temporal and Provenance Rules

Accepted facts, relations and rules have `valid_from`/`valid_to` (world time)
and `transaction_from`/`transaction_to` (knowledge-system time). Open intervals
are represented by `NULL` end values. Queries explicitly choose the temporal
axis. Provenance is a normalized record linking to source and observation plus
an evidence locator; derived traces reference the accepted fact/rule IDs and
are expanded through this chain by the Explain operation.

## Security and Operational Boundaries

The first release provides an explicit role boundary via `X-Role`/dependency
injection (READER, EDITOR, REVIEWER, ADMIN, SYSTEM) and documents replacement
with the host application's identity provider. Semantic routes are readable
without mutation privileges. Rule/ontology activation requires REVIEWER,
ADMIN or SYSTEM. Errors use stable codes and correlation IDs. JSON logs record
request and execution durations without secrets; metrics expose request, rule
execution and recomputation counters.

## Anti-patterns

- No hard-coded institution/year-specific business methods.
- No Python `eval` or arbitrary handler names in Rule DSL payloads.
- No direct database access from route handlers.
- No silent ontology mutation from an unknown concept.
- No automatic selection of an unresolved normative rule conflict.
- No treating a cached or derived value as a primary fact.
- No microservice or graph database split before measured need.
