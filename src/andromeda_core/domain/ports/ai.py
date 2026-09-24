"""AI/Jev extension ports.

Every return type is a proposal. None of these interfaces can activate an
ontology version, fact or normative rule.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    source_id: str
    locator: dict[str, Any] = field(default_factory=dict)
    excerpt_hash: str | None = None


@dataclass(frozen=True, slots=True)
class Proposal:
    proposal_type: str
    payload: dict[str, Any]
    confidence: float
    evidence: tuple[EvidenceRef, ...] = ()
    adapter: str = "unknown"


class DocumentUnderstandingPort(Protocol):
    async def extract(self, *, source_id: str, content: bytes, metadata: dict[str, Any]) -> Sequence[Proposal]: ...


class EntityResolutionPort(Protocol):
    async def resolve(self, *, candidate: dict[str, Any], candidates: Sequence[dict[str, Any]]) -> Proposal: ...


class OntologyMappingPort(Protocol):
    async def map(self, *, candidate: dict[str, Any], ontology: dict[str, Any]) -> Proposal: ...


class RuleExtractionPort(Protocol):
    async def extract_rule(self, *, source_id: str, content: bytes, ontology: dict[str, Any]) -> Proposal: ...


class ChangeInterpretationPort(Protocol):
    async def interpret(self, *, before: dict[str, Any] | None, after: dict[str, Any], evidence: EvidenceRef) -> Proposal: ...
