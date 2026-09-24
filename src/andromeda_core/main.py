"""Composition root for the Andromeda Knowledge Core ASGI application."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from andromeda_core.domain.errors import DomainError
from andromeda_core.infrastructure.config import Settings, get_settings
from andromeda_core.infrastructure.db.session import create_engine, create_session_factory
from andromeda_core.infrastructure.observability.http import CorrelationMiddleware
from andromeda_core.infrastructure.observability.logging import configure_logging, log_event
from andromeda_core.presentation.api.errors import (
    domain_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from andromeda_core.presentation.api.health import router as health_router
from andromeda_core.presentation.api.router import api_router


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)
    engine = create_engine(resolved_settings)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        log_event(logging.INFO, "app_started", environment=resolved_settings.app_env)
        yield
        await app.state.engine.dispose()
        log_event(logging.INFO, "app_stopped")

    app = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
        description=(
            "A provenance-aware semantic education knowledge core. "
            "Admin mutation routes and consumer Semantic API are separated."
        ),
        docs_url="/docs" if resolved_settings.api_docs_enabled else None,
        redoc_url="/redoc" if resolved_settings.api_docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH"],
        allow_headers=["Content-Type", "X-Role", "X-Correlation-ID", "Idempotency-Key"],
    )
    app.add_exception_handler(DomainError, domain_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)
    app.include_router(health_router)
    app.include_router(api_router)
    return app


app = create_app()
