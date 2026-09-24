# Andromeda Knowledge Core

## Purpose

Andromeda Knowledge Core is a standalone semantic backend for a versioned,
provenance-aware education knowledge system. It models ontology objects,
typed relations, temporal facts, declarative rules, derived knowledge and
dependency invalidation behind a stable Semantic API.

## Technology

- Python 3.12+ target runtime
- FastAPI and Pydantic v2
- SQLAlchemy 2.x async ORM
- PostgreSQL as the production persistence implementation
- Alembic migrations
- pytest, pytest-asyncio and Hypothesis
- Docker Compose for local development
- Ruff and mypy for quality gates
- JSON structured logging and Prometheus-compatible metrics

## Architecture

The service is a modular monolith using Explicit Architecture. Pure domain
modules define entities, value objects, ports and the deterministic Rule DSL.
Application services orchestrate use cases. Infrastructure adapters implement
PostgreSQL repositories, observability and source/AI ports. FastAPI is an
inbound adapter and never contains domain or persistence logic.

Detailed rules live in `.ai-factory/ARCHITECTURE.md`.

## Non-functional requirements

- No arbitrary code execution in the Rule DSL; never use Python `eval`.
- Facts and Derived Knowledge are separate models.
- Important data carries valid time and transaction time.
- Every accepted assertion is traceable through provenance to a source.
- Rules and ontology versions are activated atomically and are auditable.
- Administrative mutation routes are distinct from consumer Semantic API routes.
- Demo data and seed operations are idempotent.
- The core must run without external AI credentials; AI adapters are ports and mocks.
