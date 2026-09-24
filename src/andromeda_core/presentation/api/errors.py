"""Stable API error envelope and exception handlers."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from andromeda_core.domain.errors import DomainError
from andromeda_core.domain.ports.observability import correlation_id_context
from andromeda_core.infrastructure.observability.metrics import api_errors_total

logger = logging.getLogger("andromeda.api")


def error_payload(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "trace_id": correlation_id_context.get(),
        }
    }


async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
    api_errors_total.labels(exc.code).inc()
    return JSONResponse(status_code=exc.status_code, content=error_payload(exc.code, exc.message, exc.details))


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    api_errors_total.labels("VALIDATION_FAILED").inc()
    details = {"fields": [{"path": list(error.get("loc", [])), "type": error.get("type")} for error in exc.errors()]}
    return JSONResponse(status_code=422, content=error_payload("VALIDATION_FAILED", "Request validation failed.", details))


async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    api_errors_total.labels("INTERNAL_ERROR").inc()
    logger.exception("unhandled_request_error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=error_payload("INTERNAL_ERROR", "An internal error occurred. Use the trace ID for support.")
    )
