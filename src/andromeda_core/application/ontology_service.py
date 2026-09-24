"""Versioned ontology and change-proposal use cases."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from andromeda_core.application.audit_service import record_audit
from andromeda_core.application.dependency_service import DependencyService
from andromeda_core.domain.common import (
    OntologyChangeType,
    OntologyStatus,
    ProposalStatus,
    ReviewReason,
    ReviewStatus,
    utc_now,
)
from andromeda_core.domain.errors import ConflictError, NotFoundError, ValidationError
from andromeda_core.domain.ports.repositories import RepositoryPort


class OntologyService:
    def __init__(self, repo: RepositoryPort) -> None:
        self.repo = repo

    async def create_version(self, data: dict[str, Any], actor: str) -> dict[str, Any]:
        existing = next((item for item in await self.repo.list_ontologies() if item["version_code"] == data["version_code"]), None)
        if existing:
            return existing
        now = utc_now()
        previous_id = data.get("previous_version_id")
        if await self.repo.list_ontologies() and not previous_id:
            raise ValidationError("ONTOLOGY_PREVIOUS_REQUIRED", "A subsequent ontology version must name its previous version.")
        if previous_id:
            await self.repo.get_ontology(previous_id)
        ontology = await self.repo.create_ontology(
            {
                "id": str(uuid4()),
                "version_code": data["version_code"],
                "previous_version_id": previous_id,
                "status": OntologyStatus.DRAFT.value,
                "change_type": data.get("change_type", OntologyChangeType.BACKWARD_COMPATIBLE.value),
                "migration_requirements": data.get("migration_requirements"),
                "created_at": now,
                "activated_at": None,
                "row_version": 1,
            }
        )
        await record_audit(repo=self.repo, actor=actor, action="ONTOLOGY_PROPOSED", entity_type="ontology", entity_id=ontology["id"], after=ontology)
        await self.repo.commit()
        return ontology

    async def add_definition(self, ontology_id: str, kind: str, data: dict[str, Any], actor: str) -> dict[str, Any]:
        ontology = await self.repo.get_ontology(ontology_id)
        if ontology["status"] == OntologyStatus.ACTIVE.value:
            raise ConflictError("ONTOLOGY_IMMUTABLE", "Active ontology versions cannot be edited.")
        definition = await self.repo.create_definition(kind, {"id": str(uuid4()), "ontology_version_id": ontology_id, **data, **({"created_at": utc_now()} if kind == "object_type" else {})})
        await record_audit(repo=self.repo, actor=actor, action="ONTOLOGY_DEFINITION_ADDED", entity_type=kind, entity_id=definition["id"], after=definition)
        await self.repo.commit()
        return definition

    async def activate(self, ontology_id: str, actor: str, expected_version: int | None = None) -> dict[str, Any]:
        ontology = await self.repo.get_ontology(ontology_id)
        if ontology["status"] not in {OntologyStatus.DRAFT.value, OntologyStatus.VALIDATING.value, OntologyStatus.MIGRATING.value}:
            if ontology["status"] == OntologyStatus.ACTIVE.value:
                return ontology
            raise ConflictError("ONTOLOGY_INVALID_STATE", "Only a draft or validated ontology can be activated.")
        if ontology["change_type"] == OntologyChangeType.BREAKING.value and ontology["status"] != OntologyStatus.MIGRATING.value:
            raise ValidationError("MIGRATION_REQUIRED", "Breaking ontology changes must complete migration before activation.")
        active = await self.repo.get_active_ontology()
        if active and active["id"] != ontology_id:
            await self.repo.update_ontology(active["id"], {"status": OntologyStatus.SUPERSEDED.value}, active["row_version"])
            await DependencyService(self.repo).invalidate("ontology", active["id"], "Ontology version superseded.")
        activated = await self.repo.update_ontology(ontology_id, {"status": OntologyStatus.ACTIVE.value, "activated_at": utc_now()}, expected_version)
        await record_audit(repo=self.repo, actor=actor, action="ONTOLOGY_CHANGED", entity_type="ontology", entity_id=ontology_id, before=ontology, after=activated)
        await self.repo.commit()
        return activated

    async def active_view(self) -> dict[str, Any]:
        active = await self.repo.get_active_ontology()
        if not active:
            raise NotFoundError("active_ontology", "active")
        return {**active, **await self.repo.ontology_definitions(active["id"])}

    async def create_unknown_concept_proposal(
        self,
        *,
        concept_key: str,
        reason: str,
        source_evidence: dict[str, Any],
        confidence: float,
        actor: str,
    ) -> dict[str, Any]:
        existing_review = next(
            (
                item
                for item in await self.repo.list_reviews(ReviewStatus.NEEDS_REVIEW.value)
                if item["reason"] == ReviewReason.UNKNOWN_CONCEPT.value
                and item.get("proposed_change_json", {}).get("concept_key") == concept_key
            ),
            None,
        )
        if existing_review:
            return {"proposal_id": existing_review["entity_id"], "review_id": existing_review["id"], "deduplicated": True}
        proposal_id, review_id = str(uuid4()), str(uuid4())
        now = utc_now()
        await self.repo.create_review(
            {
                "id": review_id,
                "reason": ReviewReason.UNKNOWN_CONCEPT.value,
                "status": ReviewStatus.NEEDS_REVIEW.value,
                    "entity_type": "ontology_proposal",
                "entity_id": proposal_id,
                "summary": f"Unknown ontology concept: {concept_key}",
                "evidence_json": source_evidence,
                "proposed_change_json": {"concept_key": concept_key},
                "decision_json": {},
                "created_at": now,
                "updated_at": now,
                "decided_at": None,
                "decided_by": None,
                "row_version": 1,
            }
        )
        proposal = await self.repo.create_proposal(
            {
                "id": proposal_id,
                "proposed_types": [{"code": concept_key}],
                "proposed_properties": [],
                "proposed_relations": [],
                "reason": reason,
                "source_evidence": source_evidence,
                "confidence": confidence,
                "impact_analysis": {"requires_review": True},
                "status": ProposalStatus.PROPOSED.value,
                "review_id": review_id,
                "created_at": now,
                "updated_at": now,
                "row_version": 1,
            }
        )
        await record_audit(repo=self.repo, actor=actor, action="ONTOLOGY_CHANGE_PROPOSED", entity_type="ontology_proposal", entity_id=proposal_id, after=proposal)
        await self.repo.commit()
        return {"proposal_id": proposal_id, "review_id": review_id, "deduplicated": False}
