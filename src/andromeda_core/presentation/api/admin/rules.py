"""Rule administration endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from andromeda_core.application.rule_service import RuleService
from andromeda_core.infrastructure.db.repositories import CoreRepository
from andromeda_core.presentation.api.dependencies import Role, get_session, require_role
from andromeda_core.presentation.api.schemas import API_ERROR_RESPONSES, RuleCreate

router = APIRouter(prefix="/rules", tags=["admin: rules"], responses=API_ERROR_RESPONSES)


@router.post("", summary="Create a draft declarative rule", status_code=201)
async def create_rule(
    payload: RuleCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    _: Role = Depends(require_role(Role.EDITOR)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    data = payload.model_dump()
    if idempotency_key:
        data["idempotency_key"] = idempotency_key
    return await RuleService(CoreRepository(session)).create(data, "EDITOR")


@router.get("", summary="List rule versions")
async def list_rules(
    status: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    return await CoreRepository(session).list_rules(status)


@router.get("/{rule_id}", summary="Read a rule version and its tests")
async def get_rule(rule_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return await CoreRepository(session).get_rule(rule_id)


@router.post("/{rule_id}/validate", summary="Validate the Rule DSL")
async def validate_rule(
    rule_id: str,
    _: Role = Depends(require_role(Role.EDITOR)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await RuleService(CoreRepository(session)).validate(rule_id, "EDITOR")


@router.post("/{rule_id}/test", summary="Run persisted rule test cases")
async def test_rule(
    rule_id: str,
    _: Role = Depends(require_role(Role.EDITOR)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await RuleService(CoreRepository(session)).test(rule_id, "EDITOR")


@router.post("/{rule_id}/activate", summary="Activate a validated and tested rule")
async def activate_rule(
    rule_id: str,
    expected_version: int | None = Query(default=None),
    _: Role = Depends(require_role(Role.REVIEWER)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await RuleService(CoreRepository(session)).activate(rule_id, "REVIEWER", expected_version)
