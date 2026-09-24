"""Human review decisions and audit behavior."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from andromeda_core.application.audit_service import record_audit
from andromeda_core.application.knowledge_service import KnowledgeService
from andromeda_core.domain.common import ProposalStatus, ReviewStatus, utc_now
from andromeda_core.domain.errors import ConflictError, ValidationError
from andromeda_core.domain.ports.repositories import RepositoryPort


class ReviewService:
    def __init__(self, repo: RepositoryPort) -> None:
        self.repo = repo

    async def decide(self, review_id: str, action: str, actor: str, reason: str, modification: dict[str, Any] | None = None, expected_version: int | None = None) -> dict[str, Any]:
        if action not in {"approve", "reject", "modify"}:
            raise ValidationError("INVALID_REVIEW_ACTION", "Review action must be approve, reject or modify.")
        review = await self.repo.get_review(review_id)
        if review["status"] != ReviewStatus.NEEDS_REVIEW.value:
            raise ConflictError("REVIEW_ALREADY_DECIDED", "This review item already has a decision.")
        decision = {"action": action, "reason": reason, "modification": modification or {}}
        if action == "approve" and review["entity_type"] == "observation":
            observation = await self.repo.get_observation(review["entity_id"])
            if observation["status"] == "NEEDS_REVIEW":
                await self.repo.update_observation(review["entity_id"], {"status": "VALIDATED"})
            await KnowledgeService(self.repo).accept_observation(review["entity_id"], actor)
        if review["entity_type"] == "ontology_proposal" and action in {"approve", "reject", "modify"}:
            proposal = await self.repo.get_proposal(review["entity_id"])
            proposal_status = {
                "approve": ProposalStatus.APPROVED.value,
                "reject": ProposalStatus.REJECTED.value,
                "modify": ProposalStatus.MODIFIED.value,
            }[action]
            proposal_update: dict[str, Any] = {"status": proposal_status}
            if modification is not None:
                proposal_update["impact_analysis"] = {
                    **proposal.get("impact_analysis", {}),
                    "review_modification": modification,
                }
            updated_proposal = await self.repo.update_proposal(proposal["id"], proposal_update, proposal["row_version"])
            await self.repo.create_change({"id": str(uuid4()), "classification": "UNKNOWN_CONCEPT", "entity_type": "ontology_proposal", "entity_id": proposal["id"], "before_json": proposal, "after_json": updated_proposal, "reason": reason, "created_at": utc_now()})
        status = ReviewStatus.APPROVED.value if action == "approve" else ReviewStatus.REJECTED.value if action == "reject" else ReviewStatus.MODIFIED.value
        updated = await self.repo.update_review(review_id, {"status": status, "decision_json": decision, "decided_at": utc_now(), "decided_by": actor}, expected_version or review["row_version"])
        await record_audit(repo=self.repo, actor=actor, action=f"REVIEW_{status}", entity_type="review", entity_id=review_id, before=review, after=updated, reason=reason)
        await self.repo.commit()
        return updated
