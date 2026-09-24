"""Liveness, readiness and metrics endpoints."""

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import PlainTextResponse

from andromeda_core.domain.ports.observability import correlation_id_context
from andromeda_core.infrastructure.db.session import check_database
from andromeda_core.infrastructure.observability.metrics import metrics_payload

router = APIRouter(tags=["operations"])


@router.get("/health", summary="Process liveness", description="Returns liveness without requiring a database.")
async def health(request: Request) -> dict[str, str]:
    return {"status": "ok", "service": request.app.state.settings.app_name, "correlation_id": correlation_id_context.get()}


@router.get("/ready", summary="Dependency readiness", description="Checks that the configured database is reachable.")
async def ready(request: Request) -> Response:
    is_ready = await check_database(request.app.state.engine)
    if not is_ready:
        return Response(
            content='{"status":"not_ready","database":"unavailable"}',
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="application/json",
        )
    return Response(content='{"status":"ready","database":"available"}', media_type="application/json")


@router.get("/metrics", include_in_schema=False)
async def metrics() -> PlainTextResponse:
    return PlainTextResponse(metrics_payload().decode("utf-8"), media_type="text/plain; version=0.0.4")
