# Architecture

Andromeda Core is an explicit-architecture modular monolith. The dependency
direction is inward:

~~~mermaid
flowchart TB
  P[Presentation: FastAPI/OpenAPI] --> A[Application use cases]
  A --> D[Domain: DSL, rules, ontology, engine]
  A --> R[Repository and adapter ports]
  R --> I[Infrastructure: SQLAlchemy, PostgreSQL, logging]
  D --> R
~~~

The domain does not import FastAPI, SQLAlchemy, HTTP clients or an AI SDK.
Application services coordinate transactions and policy. Infrastructure
implements ports. Presentation turns HTTP into application commands and
application results into stable contracts.

## Modules

- ontology: versioned semantic definitions and controlled evolution;
- knowledge: typed objects, relations, facts, observations and sources;
- rules: rule versions, test cases, scope, exceptions and conflicts;
- rule engine: closed AST evaluator and generic effect registry;
- computation: derived materialization, trace and deterministic metadata;
- dependency: source-to-derived edges, invalidation and cycle checks;
- review/audit: human decisions and immutable operational history;
- semantic: consumer operations over global knowledge plus request context;
- ports: swappable repositories, source adapters and AI/Jev proposals.

The database is an adapter. PostgreSQL tables are normalized around the
domain concepts but do not become the public model. JSON is used for DSL ASTs,
evidence, traces and rare extensible attributes; identity, lifecycle,
temporal columns and query predicates are first-class SQL columns.

## Runtime flow

~~~mermaid
sequenceDiagram
  participant C as Client
  participant API as Semantic API
  participant S as Application service
  participant DB as PostgreSQL
  participant E as Rule Engine
  C->>API: evaluate(applicant, query context)
  API->>S: validated command
  S->>DB: active ontology/rules/facts/relations
  S->>E: immutable snapshot
  E-->>S: derived value + trace + dependencies
  S->>DB: materialized derived + dependency edges
  S-->>API: semantic response
  API-->>C: result_id, value, explanation
~~~

Activation, supersession, audit and targeted invalidation run in one database
transaction. A failed activation leaves the old active rule and its derived
projections intact.

## Extensibility

A new education policy expressed by existing AST nodes and effect kinds is
data only. A new source uses SourceAdapter and emits ObservationCandidate.
A new AI provider implements proposal ports. A different persistence adapter
implements the repository seam. Only a genuinely new computation primitive
requires a domain/engine extension.

