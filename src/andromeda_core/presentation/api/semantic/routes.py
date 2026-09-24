"""Stable consumer-oriented semantic operations."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from andromeda_core.application.computation_service import ComputationService
from andromeda_core.application.explain_service import ExplainService
from andromeda_core.application.semantic_service import SemanticService
from andromeda_core.domain.engine import RuleEngine
from andromeda_core.infrastructure.config import Settings
from andromeda_core.infrastructure.db.repositories import CoreRepository
from andromeda_core.infrastructure.observability.rule_metrics import PrometheusRuleExecutionObserver
from andromeda_core.presentation.api.dependencies import get_session, get_settings
from andromeda_core.presentation.api.schemas import (
    API_ERROR_RESPONSES,
    EvaluateRequest,
    ExplainResponse,
    SemanticEvaluateResponse,
    SemanticSimulationResponse,
    SimulateRequest,
)

router = APIRouter(prefix="/semantic", tags=["semantic"], responses=API_ERROR_RESPONSES)


def _service(session: AsyncSession, settings: Settings) -> SemanticService:
    return SemanticService(
        ComputationService(
            CoreRepository(session),
            engine=RuleEngine(PrometheusRuleExecutionObserver()),
            engine_version=settings.engine_version,
        )
    )


@router.post("/evaluate", summary="Evaluate semantic knowledge for an applicant", description="Combines canonical facts, active rules, ontology and ephemeral applicant context.")
async def evaluate(
    payload: EvaluateRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SemanticEvaluateResponse:
    result = await _service(session, settings).evaluate(payload.model_dump(mode="json"))
    return SemanticEvaluateResponse.model_validate(result)


@router.post("/simulate", summary="Run an immutable what-if overlay", description="Returns before/after/delta without mutating persisted applicant facts.")
async def simulate(
    payload: SimulateRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SemanticSimulationResponse:
    result = await _service(session, settings).simulate(payload.model_dump(mode="json"))
    return SemanticSimulationResponse.model_validate(result)


@router.get("/explain/{result_id}", summary="Explain a derived result through provenance")
async def explain(result_id: str, session: AsyncSession = Depends(get_session)) -> ExplainResponse:
    result = await ExplainService(CoreRepository(session)).explain(result_id)
    return ExplainResponse.model_validate(result)


@router.get("/programs/{program_id}", summary="Get a program semantic projection")
async def get_program(program_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    repo = CoreRepository(session)
    program = await repo.find_object(program_id)
    relations = await repo.list_relations(subject_id=program_id)
    return {"program": program, "relations": relations}


@router.get("/programs/{program_id}/curriculum", summary="Get program curriculum relations")
async def get_program_curriculum(program_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    repo = CoreRepository(session)
    program = await repo.find_object(program_id)
    relations = [item for item in await repo.list_relations(subject_id=program_id) if item["relation_type_code"] in {"HAS_CURRICULUM", "CONTAINS"}]
    return {"program_id": program_id, "program": program, "curriculum_relations": relations}
