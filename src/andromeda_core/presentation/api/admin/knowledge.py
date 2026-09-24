"""Knowledge administration and ingestion endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from andromeda_core.application.knowledge_service import KnowledgeService
from andromeda_core.infrastructure.config import Settings
from andromeda_core.infrastructure.db.repositories import CoreRepository
from andromeda_core.presentation.api.dependencies import (
    Role,
    get_session,
    get_settings,
    require_role,
)
from andromeda_core.presentation.api.schemas import (
    API_ERROR_RESPONSES,
    FactCreate,
    ObjectCreate,
    ObservationCreate,
    RelationCreate,
    SourceCreate,
)

router = APIRouter(tags=["admin: knowledge"], responses=API_ERROR_RESPONSES)


@router.post("/sources", summary="Register a first-class source", status_code=201)
async def create_source(
    payload: SourceCreate,
    _: Role = Depends(require_role(Role.EDITOR)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await KnowledgeService(CoreRepository(session)).create_source(payload.model_dump(), "EDITOR")


@router.get("/sources", summary="List sources")
async def list_sources(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    return await CoreRepository(session).list_sources()


@router.post("/observations", summary="Persist an observation from a source", status_code=201)
async def create_observation(
    payload: ObservationCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    _: Role = Depends(require_role(Role.EDITOR)),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    data = payload.model_dump()
    data["idempotency_key"] = idempotency_key or data.get("idempotency_key")
    return await KnowledgeService(CoreRepository(session), settings.confidence_review_threshold).create_observation(data, "EDITOR")


@router.get("/observations/{observation_id}", summary="Read an observation")
async def get_observation(observation_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return await CoreRepository(session).get_observation(observation_id)


@router.post("/observations/{observation_id}/accept", summary="Promote a validated observation to a fact")
async def accept_observation(
    observation_id: str,
    _: Role = Depends(require_role(Role.REVIEWER)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await KnowledgeService(CoreRepository(session)).accept_observation(observation_id, "REVIEWER")


@router.post("/objects", summary="Create a typed knowledge object", status_code=201)
async def create_object(
    payload: ObjectCreate,
    _: Role = Depends(require_role(Role.EDITOR)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await KnowledgeService(CoreRepository(session)).create_object(payload.model_dump(), "EDITOR")


@router.get("/objects", summary="List logical knowledge objects")
async def list_objects(
    object_type: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    return await CoreRepository(session).list_objects(object_type)


@router.get("/objects/{object_id}", summary="Read a knowledge object")
async def get_object(object_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return await CoreRepository(session).find_object(object_id)


@router.post("/facts", summary="Accept a canonical typed fact", status_code=201)
async def create_fact(
    payload: FactCreate,
    _: Role = Depends(require_role(Role.EDITOR)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await KnowledgeService(CoreRepository(session)).create_fact(payload.model_dump(), "EDITOR")


@router.get("/facts", summary="Query facts by valid and transaction time")
async def list_facts(
    subject_id: str | None = Query(default=None),
    property_code: str | None = Query(default=None),
    valid_at: datetime | None = Query(default=None),
    known_at: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    return await CoreRepository(session).list_facts(subject_id=subject_id, property_code=property_code, valid_at=valid_at, known_at=known_at)


@router.get("/facts/{fact_id}", summary="Read a canonical fact")
async def get_fact(fact_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return await CoreRepository(session).get_fact(fact_id)


@router.post("/relations", summary="Create a typed first-class relation", status_code=201)
async def create_relation(
    payload: RelationCreate,
    _: Role = Depends(require_role(Role.EDITOR)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await KnowledgeService(CoreRepository(session)).create_relation(payload.model_dump(), "EDITOR")


@router.get("/relations", summary="List typed relations")
async def list_relations(
    subject_id: str | None = Query(default=None),
    relation_type: str | None = Query(default=None),
    valid_at: datetime | None = Query(default=None),
    known_at: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    return await CoreRepository(session).list_relations(subject_id, relation_type, valid_at, known_at)
