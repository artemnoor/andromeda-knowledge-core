"""HTTP middleware for correlation IDs, timing and safe request metrics."""

from __future__ import annotations

import logging
import time
from uuid import UUID, uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from andromeda_core.domain.errors import PayloadTooLargeError
from andromeda_core.infrastructure.observability.logging import bind_correlation_id, log_event
from andromeda_core.infrastructure.observability.metrics import (
    api_errors_total,
    http_request_duration_seconds,
    http_requests_total,
)


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        correlation_id = _valid_correlation_id(request.headers.get("X-Correlation-ID"))
        bind_correlation_id(correlation_id)
        started = time.perf_counter()
        status_code = 500
        response: Response | None = None
        try:
            limit = request.app.state.settings.max_request_body_bytes
            content_length = request.headers.get("content-length")
            parsed_length = int(content_length) if content_length and content_length.isdigit() else None
            if parsed_length is not None and parsed_length > limit:
                error = PayloadTooLargeError(limit)
                api_errors_total.labels(error.code).inc()
                response = JSONResponse(
                    status_code=error.status_code,
                    content={"error": {"code": error.code, "message": error.message, "details": error.details, "trace_id": correlation_id}},
                )
            else:
                response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.perf_counter() - started
            path = request.url.path
            http_requests_total.labels(request.method, path, str(status_code)).inc()
            http_request_duration_seconds.labels(request.method, path).observe(duration)
            log_event(
                logging.INFO,
                "request_completed",
                method=request.method,
                path=path,
                status_code=status_code,
                duration_ms=round(duration * 1000, 3),
            )
            if response is not None:
                response.headers["X-Correlation-ID"] = correlation_id
                if request.app.state.settings.enable_security_headers:
                    response.headers["X-Content-Type-Options"] = "nosniff"
                    response.headers["X-Frame-Options"] = "DENY"
                    response.headers["Referrer-Policy"] = "no-referrer"


def _valid_correlation_id(value: str | None) -> str:
    if value:
        try:
            return str(UUID(value))
        except ValueError:
            pass
    return str(uuid4())
