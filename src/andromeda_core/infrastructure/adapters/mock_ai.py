"""Safe deterministic AI stand-ins. They emit proposals, never mutations."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

from andromeda_core.domain.ports.ai import EvidenceRef, Proposal


def _content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class MockDocumentUnderstandingAdapter:
    async def extract(self, *, source_id: str, content: bytes, metadata: dict[str, Any]) -> Sequence[Proposal]:
        return [
            Proposal(
                proposal_type="OBSERVATION_CANDIDATE",
                payload={"source_id": source_id, "metadata": {"keys": sorted(metadata)}},
                confidence=0.5,
                evidence=(EvidenceRef(source_id=source_id, locator={"content_sha256": _content_hash(content)}),),
                adapter="mock-document-understanding",
            )
        ]


class MockRuleExtractionAdapter:
    async def extract_rule(self, *, source_id: str, content: bytes, ontology: dict[str, Any]) -> Proposal:
        # The bytes are treated as untrusted evidence. No text is executed or
        # interpreted as a command, and the returned rule remains a draft.
        return Proposal(
            proposal_type="RULE_PROPOSAL",
            payload={"source_id": source_id, "ontology_version_id": ontology.get("id"), "status": "DRAFT"},
            confidence=0.0,
            evidence=(EvidenceRef(source_id=source_id, locator={"content_sha256": _content_hash(content)}),),
            adapter="mock-rule-extraction",
        )
