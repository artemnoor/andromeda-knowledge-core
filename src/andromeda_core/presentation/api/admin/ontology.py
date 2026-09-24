"""Ontology administration endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from andromeda_core.application.ontology_service import OntologyService
from andromeda_core.infrastructure.db.repositories import CoreRepository
from andromeda_core.presentation.api.dependencies import Role, get_session, require_role
from andromeda_core.presentation.api.schemas import (
    API_ERROR_RESPONSES,
    ObjectTypeCreate,
    OntologyCreate,
    PropertyDefinitionCreate,
    RelationTypeCreate,
)

router = APIRouter(prefix="/ontology", tags=["admin: ontology"], responses=API_ERROR_RESPONSES)


@router.get("/versions", summary="List ontology versions", response_model=list[dict[str, Any]])
async def list_versions(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    return await CoreRepository(session).list_ontologies()


@router.get("/versions/{ontology_id}", summary="Read an ontology version")
async def get_version(ontology_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    repo = CoreRepository(session)
    ontology = await repo.get_ontology(ontology_id)
    return {**ontology, **await repo.ontology_definitions(ontology_id)}


@router.post("/versions", summary="Create a draft ontology version", status_code=201)
async def create_version(
    payload: OntologyCreate,
    _: Role = Depends(require_role(Role.EDITOR)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await OntologyService(CoreRepository(session)).create_version(payload.model_dump(), actor="EDITOR")


@router.post("/versions/{ontology_id}/object-types", summary="Add an object type", status_code=201)
async def add_object_type(
    ontology_id: str,
    payload: ObjectTypeCreate,
    _: Role = Depends(require_role(Role.EDITOR)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await OntologyService(CoreRepository(session)).add_definition(ontology_id, "object_type", payload.model_dump(), "EDITOR")


@router.post("/versions/{ontology_id}/properties", summary="Add a typed property definition", status_code=201)
async def add_property(
    ontology_id: str,
    payload: PropertyDefinitionCreate,
    _: Role = Depends(require_role(Role.EDITOR)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await OntologyService(CoreRepository(session)).add_definition(ontology_id, "property", payload.model_dump(), "EDITOR")


@router.post("/versions/{ontology_id}/relation-types", summary="Add a relation type", status_code=201)
async def add_relation_type(
    ontology_id: str,
    payload: RelationTypeCreate,
    _: Role = Depends(require_role(Role.EDITOR)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await OntologyService(CoreRepository(session)).add_definition(ontology_id, "relation_type", payload.model_dump(), "EDITOR")


@router.post("/versions/{ontology_id}/activate", summary="Activate an ontology version")
async def activate_version(
    ontology_id: str,
    expected_version: int | None = Query(default=None),
    _: Role = Depends(require_role(Role.REVIEWER)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await OntologyService(CoreRepository(session)).activate(ontology_id, "REVIEWER", expected_version)


@router.get("/proposals", summary="List ontology change proposals")
async def list_proposals(
    status: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    return await CoreRepository(session).list_proposals(status)


@router.get("/proposals/{proposal_id}", summary="Read an ontology change proposal")
async def get_proposal(proposal_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return await CoreRepository(session).get_proposal(proposal_id)
