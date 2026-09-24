"""AI/Jev extension ports.

Every return type is a proposal. None of these interfaces can activate an
ontology version, fact or normative rule.
"""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    source_id: str
    locator: dict[str, Any] = field(default_factory=dict)
    excerpt_hash: str | None = None


@dataclass(frozen=True, slots=True)
class ExtractionContext:
    """Stable context supplied to every document extraction attempt.

    The ontology snapshot is part of the extraction contract, not optional
    adapter metadata.  Keeping it on the context makes it impossible for an
    HTTP adapter to silently omit the object/property/relation vocabulary.
    """

    source_id: str
    source_url: str
    item_key: str
    profile: str
    ontology_snapshot: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def ontology_for_prompt(self) -> dict[str, Any]:
        """Return a detached, canonical snapshot safe to serialize for an AI request."""

        snapshot = deepcopy(self.ontology_snapshot)
        snapshot["object_types"] = snapshot.get("object_types", snapshot.get("ObjectTypes", []))
        snapshot["properties"] = snapshot.get("properties", snapshot.get("Properties", []))
        snapshot["relations"] = snapshot.get("relations", snapshot.get("relation_types", snapshot.get("Relations", [])))
        return snapshot


@dataclass(frozen=True, slots=True)
class Proposal:
    proposal_type: str
    payload: dict[str, Any]
    confidence: float
    evidence: tuple[EvidenceRef, ...] = ()
    adapter: str = "unknown"


class DocumentUnderstandingPort(Protocol):
    async def extract(
        self,
        *,
        source_id: str,
        content: bytes,
        metadata: dict[str, Any],
        context: ExtractionContext | None = None,
    ) -> Sequence[Proposal]: ...


class ContextualDocumentUnderstandingPort(Protocol):
    async def extract(self, *, context: ExtractionContext, content: bytes) -> Sequence[Proposal]: ...


class EntityResolutionPort(Protocol):
    async def resolve(self, *, candidate: dict[str, Any], candidates: Sequence[dict[str, Any]]) -> Proposal: ...


class OntologyMappingPort(Protocol):
    async def map(self, *, candidate: dict[str, Any], ontology: dict[str, Any]) -> Proposal: ...


class RuleExtractionPort(Protocol):
    async def extract_rule(self, *, source_id: str, content: bytes, ontology: dict[str, Any]) -> Proposal: ...


class ChangeInterpretationPort(Protocol):
    async def interpret(self, *, before: dict[str, Any] | None, after: dict[str, Any], evidence: EvidenceRef) -> Proposal: ...
