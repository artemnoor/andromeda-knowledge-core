"""Read-only operational views for changes and audit events."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from andromeda_core.infrastructure.db.repositories import CoreRepository
from andromeda_core.presentation.api.dependencies import Role, get_session, require_role
from andromeda_core.presentation.api.schemas import API_ERROR_RESPONSES

router = APIRouter(tags=["admin: operations"], responses=API_ERROR_RESPONSES)


@router.get("/changes", summary="List classified knowledge changes")
async def list_changes(
    classification: str | None = Query(default=None),
    _: Role = Depends(require_role(Role.REVIEWER)),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    return await CoreRepository(session).list_changes(classification)


@router.get("/audit", summary="List audit events")
async def list_audit(
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    _: Role = Depends(require_role(Role.REVIEWER)),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    return await CoreRepository(session).list_audit(entity_type, entity_id)
