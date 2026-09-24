"""Ports for source ingestion adapters.

Adapters stop at observation candidates. They never receive a repository and
cannot create canonical facts or relations directly.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from andromeda_core.domain.common import SourceType


@dataclass(frozen=True, slots=True)
class SourceDescriptor:
    source_id: str
    source_type: SourceType
    locator: str
    checksum: str | None = None


@dataclass(frozen=True, slots=True)
class ObservationCandidate:
    subject_candidate: dict[str, Any]
    property_candidate: str | None
    relation_candidate: dict[str, Any] | None
    value: Any
    value_type: str | None
    evidence: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SourceFetchResult:
    source: SourceDescriptor
    content: bytes
    content_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SourceAdapter(Protocol):
    source_type: SourceType

    async def fetch(self, source: SourceDescriptor) -> SourceFetchResult: ...

    async def parse(self, fetched: SourceFetchResult) -> Sequence[ObservationCandidate]: ...
