"""Derived knowledge and dependency diagnostics."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from andromeda_core.application.dependency_service import DependencyService
from andromeda_core.infrastructure.db.repositories import CoreRepository
from andromeda_core.presentation.api.dependencies import Role, get_session, require_role
from andromeda_core.presentation.api.schemas import API_ERROR_RESPONSES

router = APIRouter(prefix="/derived", tags=["admin: derived"], responses=API_ERROR_RESPONSES)


@router.get("/{derived_id}", summary="Read a materialized derived value")
async def get_derived(derived_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return await CoreRepository(session).get_derived(derived_id)


@router.get("/{derived_id}/dependencies", summary="Read dependency edges for a derived value")
async def get_dependencies(derived_id: str, session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    return await CoreRepository(session).dependencies_to("derived", derived_id)


@router.post("/{derived_id}/invalidate", summary="Invalidate a derived projection")
async def invalidate_derived(
    derived_id: str,
    _: Role = Depends(require_role(Role.ADMIN)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    report = await DependencyService(CoreRepository(session)).invalidate("derived", derived_id, "Administrative invalidation.")
    await session.commit()
    return report
