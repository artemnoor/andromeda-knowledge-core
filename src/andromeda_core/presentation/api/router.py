"""Versioned API router composition."""

from fastapi import APIRouter

from andromeda_core.presentation.api.admin.derived import router as derived_router
from andromeda_core.presentation.api.admin.knowledge import router as knowledge_router
from andromeda_core.presentation.api.admin.ontology import router as ontology_router
from andromeda_core.presentation.api.admin.operations import router as operations_router
from andromeda_core.presentation.api.admin.reviews import router as reviews_router
from andromeda_core.presentation.api.admin.rules import router as rules_router
from andromeda_core.presentation.api.semantic.routes import router as semantic_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(ontology_router)
api_router.include_router(knowledge_router)
api_router.include_router(rules_router)
api_router.include_router(derived_router)
api_router.include_router(reviews_router)
api_router.include_router(semantic_router)
api_router.include_router(operations_router)
