from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

import httpx
import pytest

from andromeda_core.application.ingestion_pipeline import IngestionPipelineService
from andromeda_core.domain.ports.ai import EvidenceRef, ExtractionContext, Proposal
from andromeda_core.domain.ports.ingestion import PipelineStatus
from andromeda_core.infrastructure.adapters.discovery import DiscoveryMode, HttpDiscoveryAdapter
from andromeda_core.infrastructure.adapters.evidence import build_evidence_locator
from andromeda_core.infrastructure.adapters.http_source import (
    HttpSourceFetcher,
    SourceFetchError,
    validate_source_url,
)
from andromeda_core.infrastructure.adapters.structured_json_ai import StructuredJsonHttpAIAdapter


class MemoryPipelineStore:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def find_latest_pipeline(self, pipeline_key: str) -> dict[str, Any] | None:
        matches = [row for row in self.rows if row["pipeline_key"] == pipeline_key]
        return deepcopy(matches[-1]) if matches else None

    async def find_pipeline_by_checksum(self, pipeline_key: str, checksum: str) -> dict[str, Any] | None:
        matches = [row for row in self.rows if row["pipeline_key"] == pipeline_key and row["document_checksum"] == checksum]
        return deepcopy(matches[-1]) if matches else None

    async def create_pipeline(self, data: dict[str, Any]) -> dict[str, Any]:
        row = deepcopy(data)
        row["id"] = f"pipeline-{len(self.rows) + 1}"
        self.rows.append(row)
        return deepcopy(row)

    async def update_pipeline(self, pipeline_id: str, data: dict[str, Any]) -> dict[str, Any]:
        row = next(item for item in self.rows if item["id"] == pipeline_id)
        row.update(deepcopy(data))
        return deepcopy(row)


class SequenceFetcher:
    def __init__(self, contents: list[bytes]) -> None:
        self.contents = contents
        self.calls = 0

    async def fetch(self, context: ExtractionContext) -> dict[str, Any]:
        content = self.contents[min(self.calls, len(self.contents) - 1)]
        self.calls += 1
        return {"content": content, "content_type": "text/html", "metadata": {"url": context.source_url}}


class RecordingExtractor:
    def __init__(self) -> None:
        self.calls = 0
        self.contexts: list[ExtractionContext] = []

    async def extract(self, *, context: ExtractionContext, content: bytes) -> list[Proposal]:
        self.calls += 1
        self.contexts.append(context)
        return [
            Proposal(
                proposal_type="OBSERVATION_CANDIDATE",
                payload={"content": content.decode("utf-8")},
                confidence=0.9,
                evidence=(EvidenceRef(source_id=context.source_id, locator={"content_sha256": hashlib.sha256(content).hexdigest()}),),
                adapter="fixture",
            )
        ]


class RecordingPublisher:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.calls = 0

    async def publish(self, *, context: ExtractionContext, proposals: list[Proposal], document_checksum: str) -> dict[str, Any]:
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("core unavailable")
        return {"published": len(proposals), "checksum": document_checksum, "source_id": context.source_id}


def context() -> ExtractionContext:
    return ExtractionContext(
        source_id="source-1",
        source_url="https://example.edu/admission.html",
        item_key="admission",
        profile="education-v1",
        ontology_snapshot={
            "object_types": [{"code": "University"}],
            "properties": [{"code": "admission.deadline", "value_type": "date"}],
            "relations": [{"code": "OFFERS"}],
        },
    )


@pytest.mark.asyncio
async def test_published_pipeline_rechecks_source_and_detects_changed_document() -> None:
    store = MemoryPipelineStore()
    fetcher = SequenceFetcher([b"version-1", b"version-2", b"version-2"])
    extractor = RecordingExtractor()
    publisher = RecordingPublisher()
    service = IngestionPipelineService(store=store, fetcher=fetcher, extractor=extractor, publisher=publisher)

    first = await service.run(context())
    second = await service.run(context())
    third = await service.run(context())

    assert first.status is PipelineStatus.PUBLISHED
    assert second.status is PipelineStatus.PUBLISHED
    assert second.document_checksum != first.document_checksum
    assert third.status is PipelineStatus.SKIPPED_UNCHANGED
    assert fetcher.calls == 3
    assert extractor.calls == 2
    assert publisher.calls == 2


@pytest.mark.asyncio
async def test_publish_retry_resumes_from_saved_extraction_without_fetching_again() -> None:
    store = MemoryPipelineStore()
    fetcher = SequenceFetcher([b"stable-document"])
    extractor = RecordingExtractor()
    publisher = RecordingPublisher(failures=1)
    service = IngestionPipelineService(store=store, fetcher=fetcher, extractor=extractor, publisher=publisher)

    with pytest.raises(RuntimeError, match="core unavailable"):
        await service.run(context())

    retry = await service.run(context())

    assert retry.status is PipelineStatus.PUBLISHED
    assert fetcher.calls == 1
    assert extractor.calls == 1
    assert publisher.calls == 2
    assert store.commits >= 5


@pytest.mark.asyncio
async def test_structured_json_adapter_sends_full_ontology_snapshot_to_llm() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"proposals": []}'}}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://llm.example")
    adapter = StructuredJsonHttpAIAdapter(client=client, endpoint="/chat/completions", model="test-model")

    await adapter.extract(context=context(), content=b"document")
    await client.aclose()

    assert captured["ontology_snapshot"] == context().ontology_snapshot
    system_content = captured["messages"][0]["content"]
    assert "University" in system_content
    assert "admission.deadline" in system_content
    assert "OFFERS" in system_content


def test_http_source_fetcher_rejects_private_and_credentialed_urls() -> None:
    with pytest.raises(SourceFetchError):
        validate_source_url("http://127.0.0.1/internal")
    with pytest.raises(SourceFetchError):
        validate_source_url("https://user:password@example.edu/private")


@pytest.mark.asyncio
async def test_http_source_fetcher_turns_http_errors_into_safe_source_errors() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.edu")
    fetcher = HttpSourceFetcher(client=client, resolve_host=lambda _: ["93.184.216.34"])

    with pytest.raises(SourceFetchError, match="status 404"):
        await fetcher.fetch("https://example.edu/missing")
    await client.aclose()


@pytest.mark.asyncio
async def test_discovery_supports_sitemap_and_html_links_with_same_origin_bounds() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sitemap.xml":
            return httpx.Response(200, text="<urlset><url><loc>https://example.edu/a</loc></url><url><loc>https://other.test/b</loc></url></urlset>")
        return httpx.Response(200, text='<a href="/programs">Programs</a><a href="https://other.test/private">Private</a>')

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = HttpSourceFetcher(client=client, resolve_host=lambda _: ["93.184.216.34"])
    discovery = HttpDiscoveryAdapter(fetcher=fetcher, allowed_hosts={"example.edu"})

    sitemap = await discovery.discover("https://example.edu/sitemap.xml", DiscoveryMode.SITEMAP_URL)
    links = await discovery.discover("https://example.edu/index.html", DiscoveryMode.HTML_LINKS)

    assert [item.locator for item in sitemap] == ["https://example.edu/a"]
    assert [item.locator for item in links] == ["https://example.edu/programs"]
    await client.aclose()


def test_evidence_locator_anchors_html_and_pdf_quotes_to_document_hash() -> None:
    html = build_evidence_locator(b"<html><body><h1>Admission deadline</h1></body></html>", content_type="text/html", quote="Admission deadline")
    pdf = build_evidence_locator(b"%PDF-1.7\fquota", content_type="application/pdf", quote="quota")

    assert html["format"] == "html"
    assert html["char_start"] is not None
    assert len(html["content_sha256"]) == 64
    assert pdf["format"] == "pdf"
    assert pdf["page"] == 2
    assert pdf["byte_start"] is not None
