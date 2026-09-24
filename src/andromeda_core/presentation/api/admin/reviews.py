"""Human-in-the-loop review queue endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from andromeda_core.application.review_service import ReviewService
from andromeda_core.infrastructure.db.repositories import CoreRepository
from andromeda_core.presentation.api.dependencies import Role, get_session, require_role
from andromeda_core.presentation.api.schemas import API_ERROR_RESPONSES, ReviewDecision

router = APIRouter(prefix="/reviews", tags=["admin: review"], responses=API_ERROR_RESPONSES)


@router.get("", summary="List items awaiting human review")
async def list_reviews(
    status: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    return await CoreRepository(session).list_reviews(status)


@router.get("/{review_id}", summary="Read a review item")
async def get_review(review_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return await CoreRepository(session).get_review(review_id)


@router.post("/{review_id}/approve", summary="Approve a review item")
async def approve_review(
    review_id: str,
    payload: ReviewDecision,
    _: Role = Depends(require_role(Role.REVIEWER)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await ReviewService(CoreRepository(session)).decide(review_id, "approve", "REVIEWER", payload.reason, payload.modification, payload.version)


@router.post("/{review_id}/reject", summary="Reject a review item")
async def reject_review(
    review_id: str,
    payload: ReviewDecision,
    _: Role = Depends(require_role(Role.REVIEWER)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await ReviewService(CoreRepository(session)).decide(review_id, "reject", "REVIEWER", payload.reason, payload.modification, payload.version)


@router.post("/{review_id}/modify", summary="Record a modified review decision")
async def modify_review(
    review_id: str,
    payload: ReviewDecision,
    _: Role = Depends(require_role(Role.REVIEWER)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await ReviewService(CoreRepository(session)).decide(review_id, "modify", "REVIEWER", payload.reason, payload.modification, payload.version)
