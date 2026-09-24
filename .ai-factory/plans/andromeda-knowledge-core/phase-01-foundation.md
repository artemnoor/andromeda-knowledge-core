# Phase 1: Foundation and Architecture

Plan: [index.md](index.md)
Tasks: 1-3
Depends on: none

## Objective

Create the runnable Python/FastAPI application shell, validated configuration,
stable error envelope, role boundary, correlation-aware structured logging,
health/readiness endpoints and the explicit architecture skeleton.

## Current-Code Evidence

The repository is empty. `.ai-factory/DESCRIPTION.md` and
`.ai-factory/ARCHITECTURE.md` are the only pre-existing project artifacts and
define the technology target and inward dependency rules.

## Files to Change

| Path | Action | Required change |
|------|--------|-----------------|
| `pyproject.toml` | create | Pin runtime/development dependencies and Ruff/mypy/pytest settings. |
| `.env.example` | create | Document non-secret local configuration. |
| `.gitignore` | create | Exclude environments, caches, `.env`, reports and local DB files. |
| `src/andromeda_core/main.py` | create | Composition root and application factory. |
| `src/andromeda_core/infrastructure/config.py` | create | Pydantic settings with safe defaults. |
| `src/andromeda_core/presentation/api/errors.py` | create | Stable `ApiError` and exception handlers. |
| `src/andromeda_core/infrastructure/observability/*` | create | JSON logging, correlation ID middleware and metrics. |
| `src/andromeda_core/presentation/api/health.py` | create | `/health`, `/ready`, `/metrics`. |
| `src/andromeda_core/presentation/api/dependencies.py` | create | Request role dependency and DB session seam. |
| `tests/unit/test_foundation.py` | create | Configuration, error and correlation behavior. |

## Task 1: Bootstrap the application and dependency policy

### Intent

Give every later module a stable import root and a reproducible local/runtime
environment. The application must import without a database connection.

### Implementation Steps

1. Create the `src/andromeda_core` package and explicit subpackages for domain,
   application, infrastructure and presentation.
2. Add pinned lower/upper-compatible dependency ranges in `pyproject.toml`:
   FastAPI, Pydantic Settings, SQLAlchemy async, asyncpg, Alembic, aiosqlite,
   structlog, prometheus-client, pytest, pytest-asyncio, HTTPX, Hypothesis,
   Ruff and mypy.
3. Configure Ruff and mypy to fail on changed source errors while allowing
   SQLAlchemy declarative typing pragmatically.
4. Add `.env.example` for `APP_ENV`, `APP_NAME`, `LOG_LEVEL`, `DATABASE_URL`,
   `TEST_DATABASE_URL`, `ENGINE_VERSION`, `AUTO_SEED`, and `API_DOCS_ENABLED`.

### Required Interfaces and Contracts

- Python target is 3.12+; the current verification host also ran the source
  checks under Python 3.11 where the installed toolchain required it.
  test interpreter when feasible.
- No secret is stored in repository files; `.env` is ignored.
- `create_app(settings: Settings | None = None) -> FastAPI` is the only app
  factory used by tests and the ASGI server.

### Error Handling and Logging

Import/configuration failures are raised at startup with a safe message. The
settings object must never log passwords or full DSNs. Log `app_started` once
at INFO and configuration validation failures at ERROR without secret values.

### Tests

- Import `create_app` with no environment variables.
- Verify `.env` is ignored and `.env.example` has all referenced variables.
- Run `python -m compileall src` and `ruff check src tests`.

### Acceptance Criteria

The package imports, `create_app()` returns a FastAPI application, and the
development server can expose OpenAPI without touching PostgreSQL.

### Verification

- `python -c "from andromeda_core.main import create_app; print(create_app().title)"`
- Expected result: `Andromeda Knowledge Core` is printed.

## Task 2: Add API errors, roles and observability

### Intent

Make operational behavior consistent before domain routes are added.

### Implementation Steps

1. Define `ApiError(code, message, details, status_code)` and a single response
   shape `{error:{code,message,details,trace_id}}`.
2. Install handlers for domain errors, Pydantic validation errors and unknown
   exceptions. Unknown errors return `INTERNAL_ERROR` and expose only the
   correlation ID.
3. Add middleware to accept/generate `X-Correlation-ID`, time each request,
   emit a JSON record and return the same header.
4. Add Prometheus counters/histograms for requests, rule executions and
   recomputation; expose them at `/metrics`.
5. Define `Role` (`READER`, `EDITOR`, `REVIEWER`, `ADMIN`, `SYSTEM`) and
   `require_role(...)`. In development, an absent role is `READER`; mutation
   routes explicitly require stronger roles.

### Required Interfaces and Contracts

- Correlation IDs are UUID strings when not supplied; a malformed supplied ID
  is replaced, not reflected into logs.
- Client-safe error messages never include SQL, traceback, filesystem paths,
  DSNs, or upstream payloads.
- Semantic consumers cannot pass the role dependency required by activation.

### Error Handling and Logging

Log request method/path/status/duration/correlation ID. Log exception details
server-side with traceback at ERROR; return stable generic error payload.
Never log request bodies by default because they may contain applicant data.

### Tests

- Request returns/propagates `X-Correlation-ID`.
- Invalid input returns `VALIDATION_FAILED` envelope.
- Missing role on an admin route returns `FORBIDDEN`.
- `/metrics` is valid Prometheus text.

### Acceptance Criteria

Every future route automatically has correlation, duration and safe error
behavior without route-local boilerplate.

### Verification

- `pytest -q tests/unit/test_foundation.py`
- Expected result: all foundation tests pass.

## Task 3: Compose database session and health boundaries

### Intent

Provide a DB port without coupling health and routes to ORM internals.

### Implementation Steps

1. Add `infrastructure/db/session.py` with async engine/sessionmaker factory.
2. Add `get_session()` as a FastAPI dependency and `check_database()` adapter.
3. Implement `/health` as process liveness and `/ready` as database readiness.
4. Do not call `Base.metadata.create_all()` or migrations from application
   startup; readiness reports `503` until the configured schema is available.

### Required Interfaces and Contracts

- `DATABASE_URL` supports `postgresql+asyncpg://...` in production and
  `sqlite+aiosqlite://...` in tests.
- Engine pool settings are configurable and bounded.
- Health response is machine-readable with `status`, `service`, and
  `correlation_id`; readiness includes `database` status only when safe.

### Error Handling and Logging

Database check timeouts produce `NOT_READY` with no connection string. Log
readiness failures at WARNING with correlation ID.

### Tests

- Liveness succeeds without a DB.
- Readiness succeeds/fails against a test engine fixture.
- No startup event runs schema creation.

### Acceptance Criteria

Docker can run migrations before the API and `/ready` accurately reflects the
database availability.

### Verification

- `pytest -q tests/unit/test_foundation.py`
- `python -c "from andromeda_core.main import create_app; print('/ready' in [r.path for r in create_app().routes])"`

## Phase Risks and Mitigations

- Risk: async database drivers are unavailable locally. Mitigation: retain a
  SQLite async test adapter and make PostgreSQL the documented compose path.
- Risk: framework errors leak details. Mitigation: centralize all exception
  handlers and assert the response contract in tests.

## Phase Completion Checklist

- Tasks 1-3 meet their acceptance criteria.
- Foundation checks pass.
- `index.md` task statuses are updated after verification.
