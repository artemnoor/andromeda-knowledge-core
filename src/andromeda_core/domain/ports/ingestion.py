"""Contracts for durable source-to-Core ingestion attempts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from andromeda_core.domain.ports.ai import ExtractionContext, Proposal


class PipelineStage(StrEnum):
    FETCH = "FETCH"
    EXTRACT = "EXTRACT"
    PUBLISH = "PUBLISH"


class PipelineStatus(StrEnum):
    PENDING = "PENDING"
    FETCHED = "FETCHED"
    EXTRACTED = "EXTRACTED"
    PUBLISHED = "PUBLISHED"
    SKIPPED_UNCHANGED = "SKIPPED_UNCHANGED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class FetchedDocument:
    content: bytes
    content_type: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


class IngestionFetcherPort(Protocol):
    async def fetch(self, context: ExtractionContext) -> FetchedDocument: ...


class IngestionExtractorPort(Protocol):
    async def extract(self, *, context: ExtractionContext, content: bytes) -> Sequence[Proposal]: ...


class CorePublisherPort(Protocol):
    async def publish(
        self,
        *,
        context: ExtractionContext,
        proposals: Sequence[Proposal],
        document_checksum: str,
    ) -> Mapping[str, Any]: ...


class PipelineStorePort(Protocol):
    async def commit(self) -> None: ...

    async def find_latest_pipeline(self, pipeline_key: str) -> dict[str, Any] | None: ...

    async def find_pipeline_by_checksum(self, pipeline_key: str, document_checksum: str) -> dict[str, Any] | None: ...

    async def create_pipeline(self, data: dict[str, Any]) -> dict[str, Any]: ...

    async def update_pipeline(self, pipeline_id: str, data: dict[str, Any]) -> dict[str, Any]: ...
