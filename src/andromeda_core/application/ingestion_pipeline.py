"""Durable, resumable source-to-Core ingestion orchestration."""

from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from andromeda_core.domain.identity import identity_hash, new_id
from andromeda_core.domain.ports.ai import EvidenceRef, ExtractionContext, Proposal
from andromeda_core.domain.ports.ingestion import (
    CorePublisherPort,
    FetchedDocument,
    IngestionExtractorPort,
    IngestionFetcherPort,
    PipelineStage,
    PipelineStatus,
    PipelineStorePort,
)
from andromeda_core.domain.ports.sources import SourceFetchResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PipelineRunResult:
    pipeline_id: str
    pipeline_key: str
    status: PipelineStatus
    document_checksum: str | None
    resumed_from: PipelineStage | None = None
    published: Mapping[str, Any] | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _fix_debug_enabled() -> bool:
    return os.getenv("DEBUG_FIX", "").lower() in {"1", "true", "yes"} or logger.isEnabledFor(logging.DEBUG)


def _log_debug(message: str, **fields: Any) -> None:
    if _fix_debug_enabled():
        logger.debug("[FIX:ingestion] %s", message, extra={"fix": True, **fields})


def _checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _safe_error(error: Exception) -> str:
    value = str(error).strip().replace("\n", " ")
    return value[:500] or error.__class__.__name__


def _proposal_to_dict(proposal: Proposal) -> dict[str, Any]:
    return {
        "proposal_type": proposal.proposal_type,
        "payload": proposal.payload,
        "confidence": proposal.confidence,
        "evidence": [
            {"source_id": item.source_id, "locator": item.locator, "excerpt_hash": item.excerpt_hash}
            for item in proposal.evidence
        ],
        "adapter": proposal.adapter,
    }


def _proposal_from_dict(payload: Mapping[str, Any]) -> Proposal:
    evidence = tuple(
        EvidenceRef(
            source_id=str(item.get("source_id", "")),
            locator=dict(item.get("locator", {})),
            excerpt_hash=item.get("excerpt_hash"),
        )
        for item in payload.get("evidence", [])
        if isinstance(item, Mapping)
    )
    return Proposal(
        proposal_type=str(payload.get("proposal_type", "OBSERVATION_CANDIDATE")),
        payload=dict(payload.get("payload", {})),
        confidence=float(payload.get("confidence", 0)),
        evidence=evidence,
        adapter=str(payload.get("adapter", "unknown")),
    )


def _normalise_fetched(value: FetchedDocument | SourceFetchResult | Mapping[str, Any]) -> FetchedDocument:
    if isinstance(value, FetchedDocument):
        return value
    if isinstance(value, SourceFetchResult):
        return FetchedDocument(content=value.content, content_type=value.content_type, metadata=value.metadata)
    content = value.get("content")
    if not isinstance(content, bytes):
        raise TypeError("Fetcher must return bytes content.")
    metadata = value.get("metadata", {})
    return FetchedDocument(
        content=content,
        content_type=value.get("content_type"),
        metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
    )


class IngestionPipelineService:
    """Run an ingestion attempt while preserving every successful stage.

    A stable source/item/profile key identifies the stream of attempts, not a
    forever-cache entry.  Published attempts always fetch the source again;
    incomplete attempts resume from their persisted payload instead.
    """

    def __init__(
        self,
        *,
        store: PipelineStorePort,
        fetcher: IngestionFetcherPort,
        extractor: IngestionExtractorPort,
        publisher: CorePublisherPort,
    ) -> None:
        self.store = store
        self.fetcher = fetcher
        self.extractor = extractor
        self.publisher = publisher

    async def _create_pipeline(self, data: dict[str, Any]) -> dict[str, Any]:
        row = await self.store.create_pipeline(data)
        await self.store.commit()
        return row

    async def _update_pipeline(self, pipeline_id: str, data: dict[str, Any]) -> dict[str, Any]:
        row = await self.store.update_pipeline(pipeline_id, data)
        await self.store.commit()
        return row

    async def run(self, context: ExtractionContext) -> PipelineRunResult:
        pipeline_key = identity_hash("source-pipeline", context.source_url, context.item_key, context.profile)
        current = await self.store.find_latest_pipeline(pipeline_key)
        _log_debug(
            "starting pipeline",
            source_id=context.source_id,
            pipeline_key=pipeline_key[:16],
            status=current.get("status") if current else None,
        )

        if current and current.get("status") in {PipelineStatus.PUBLISHED.value, PipelineStatus.SKIPPED_UNCHANGED.value}:
            return await self._refresh_published(current, context, pipeline_key)

        if current is None:
            current = await self._create_pipeline(self._new_pipeline(context, pipeline_key))
        return await self._continue(current, context)

    async def _refresh_published(
        self,
        current: dict[str, Any],
        context: ExtractionContext,
        pipeline_key: str,
    ) -> PipelineRunResult:
        """Re-fetch terminal attempts so an updated document gets a new attempt."""

        try:
            fetched = _normalise_fetched(await self.fetcher.fetch(context))
            checksum = _checksum(fetched.content)
        except Exception as error:
            logger.exception(
                "[FIX:ingestion] source refresh failed",
                extra={"fix": True, "source_id": context.source_id, "pipeline_key": pipeline_key[:16]},
            )
            raise error

        if checksum == current.get("document_checksum"):
            updated = await self._update_pipeline(
                current["id"],
                {"status": PipelineStatus.SKIPPED_UNCHANGED.value, "last_run_at": _now(), "last_error": None},
            )
            _log_debug("source checked and was unchanged", source_id=context.source_id, checksum=checksum[:16])
            return self._result(updated)

        existing = await self.store.find_pipeline_by_checksum(pipeline_key, checksum)
        if existing and existing.get("status") not in {PipelineStatus.PUBLISHED.value, PipelineStatus.SKIPPED_UNCHANGED.value}:
            updated = await self._update_pipeline(
                existing["id"],
                {
                    "fetched_content": fetched.content,
                    "content_type": fetched.content_type,
                    "fetch_metadata_json": dict(fetched.metadata),
                    "last_run_at": _now(),
                    "last_error": None,
                },
            )
            return await self._continue(updated, context)

        if existing:
            updated = await self._update_pipeline(
                existing["id"], {"status": PipelineStatus.SKIPPED_UNCHANGED.value, "last_run_at": _now(), "last_error": None}
            )
            return self._result(updated)

        attempt = await self._create_pipeline(self._new_pipeline(context, pipeline_key, checksum))
        updated = await self._update_pipeline(
            attempt["id"],
            {
                "status": PipelineStatus.FETCHED.value,
                "last_successful_stage": PipelineStage.FETCH.value,
                "fetched_content": fetched.content,
                "content_type": fetched.content_type,
                "fetch_metadata_json": dict(fetched.metadata),
                "last_run_at": _now(),
                "last_error": None,
            },
        )
        _log_debug("source changed; created a new attempt", source_id=context.source_id, checksum=checksum[:16])
        return await self._continue(updated, context)

    async def _continue(self, pipeline: dict[str, Any], context: ExtractionContext) -> PipelineRunResult:
        if pipeline.get("extraction_json"):
            return await self._publish(pipeline, context)
        if pipeline.get("fetched_content") is not None:
            return await self._extract(pipeline, context)
        return await self._fetch(pipeline, context)

    async def _fetch(self, pipeline: dict[str, Any], context: ExtractionContext) -> PipelineRunResult:
        try:
            fetched = _normalise_fetched(await self.fetcher.fetch(context))
            checksum = _checksum(fetched.content)
            updated = await self._update_pipeline(
                pipeline["id"],
                {
                    "document_checksum": checksum,
                    "status": PipelineStatus.FETCHED.value,
                    "last_successful_stage": PipelineStage.FETCH.value,
                    "failed_stage": None,
                    "fetched_content": fetched.content,
                    "content_type": fetched.content_type,
                    "fetch_metadata_json": dict(fetched.metadata),
                    "last_run_at": _now(),
                    "last_error": None,
                },
            )
            _log_debug("fetch stage completed", pipeline_id=pipeline["id"], checksum=checksum[:16])
            return await self._continue(updated, context)
        except Exception as error:
            await self._mark_failed(pipeline, PipelineStage.FETCH, error)
            raise

    async def _extract(self, pipeline: dict[str, Any], context: ExtractionContext) -> PipelineRunResult:
        content = pipeline.get("fetched_content")
        if not isinstance(content, bytes):
            return await self._fetch(pipeline, context)
        metadata = pipeline.get("fetch_metadata_json") or {}
        extraction_context = replace(context, metadata={**context.metadata, **metadata})
        try:
            proposals = list(await self.extractor.extract(context=extraction_context, content=content))
            updated = await self._update_pipeline(
                pipeline["id"],
                {
                    "status": PipelineStatus.EXTRACTED.value,
                    "last_successful_stage": PipelineStage.EXTRACT.value,
                    "failed_stage": None,
                    "extraction_json": [_proposal_to_dict(item) for item in proposals],
                    "last_run_at": _now(),
                    "last_error": None,
                },
            )
            _log_debug("extraction stage completed", pipeline_id=pipeline["id"], proposal_count=len(proposals))
            return await self._publish(updated, extraction_context)
        except Exception as error:
            await self._mark_failed(pipeline, PipelineStage.EXTRACT, error)
            raise

    async def _publish(self, pipeline: dict[str, Any], context: ExtractionContext) -> PipelineRunResult:
        proposals = [_proposal_from_dict(item) for item in pipeline.get("extraction_json", [])]
        try:
            published = await self.publisher.publish(
                context=context,
                proposals=proposals,
                document_checksum=str(pipeline.get("document_checksum", "")),
            )
            updated = await self._update_pipeline(
                pipeline["id"],
                {
                    "status": PipelineStatus.PUBLISHED.value,
                    "last_successful_stage": PipelineStage.PUBLISH.value,
                    "failed_stage": None,
                    "publish_result_json": dict(published),
                    "last_run_at": _now(),
                    "last_error": None,
                },
            )
            _log_debug("publish stage completed", pipeline_id=pipeline["id"], proposal_count=len(proposals))
            return self._result(updated, published=dict(published))
        except Exception as error:
            await self._mark_failed(pipeline, PipelineStage.PUBLISH, error)
            raise

    async def _mark_failed(self, pipeline: dict[str, Any], stage: PipelineStage, error: Exception) -> None:
        message = _safe_error(error)
        await self._update_pipeline(
            pipeline["id"],
            {"status": PipelineStatus.FAILED.value, "failed_stage": stage.value, "last_run_at": _now(), "last_error": message},
        )
        logger.exception(
            "[FIX:ingestion] pipeline stage failed",
            extra={"fix": True, "pipeline_id": pipeline["id"], "stage": stage.value},
        )

    def _new_pipeline(
        self,
        context: ExtractionContext,
        pipeline_key: str,
        document_checksum: str = "",
    ) -> dict[str, Any]:
        now = _now()
        return {
            "id": new_id(),
            "pipeline_key": pipeline_key,
            "source_id": context.source_id,
            "source_url": context.source_url,
            "item_key": context.item_key,
            "profile": context.profile,
            "document_checksum": document_checksum,
            "status": PipelineStatus.PENDING.value,
            "last_successful_stage": None,
            "failed_stage": None,
            "fetched_content": None,
            "content_type": None,
            "fetch_metadata_json": {},
            "extraction_json": [],
            "publish_result_json": {},
            "last_error": None,
            "created_at": now,
            "updated_at": now,
            "last_run_at": now,
        }

    def _result(self, pipeline: dict[str, Any], published: Mapping[str, Any] | None = None) -> PipelineRunResult:
        stage = pipeline.get("last_successful_stage")
        return PipelineRunResult(
            pipeline_id=str(pipeline["id"]),
            pipeline_key=str(pipeline["pipeline_key"]),
            status=PipelineStatus(str(pipeline["status"])),
            document_checksum=pipeline.get("document_checksum") or None,
            resumed_from=PipelineStage(stage) if stage else None,
            published=published if published is not None else pipeline.get("publish_result_json"),
        )
