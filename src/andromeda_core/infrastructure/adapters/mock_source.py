"""Deterministic source adapter used by tests and local demonstrations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from andromeda_core.domain.common import SourceType
from andromeda_core.domain.ports.ai import ExtractionContext
from andromeda_core.domain.ports.sources import (
    ObservationCandidate,
    SourceAdapter,
    SourceDescriptor,
    SourceFetchResult,
)


class MockSourceAdapter(SourceAdapter):
    source_type = SourceType.IMPORT

    async def fetch(self, source: SourceDescriptor | ExtractionContext) -> SourceFetchResult:
        if isinstance(source, ExtractionContext):
            source = SourceDescriptor(source_id=source.source_id, source_type=self.source_type, locator=source.source_url)
        payload = {"source_id": source.source_id, "locator": source.locator, "kind": "mock"}
        content = json.dumps(payload, sort_keys=True).encode("utf-8")
        return SourceFetchResult(source=source, content=content, content_type="application/json", metadata={"checksum": hashlib.sha256(content).hexdigest()})

    async def parse(self, fetched: SourceFetchResult) -> Sequence[ObservationCandidate]:
        payload = json.loads(fetched.content.decode("utf-8"))
        return [
            ObservationCandidate(
                subject_candidate={"stable_key": f"mock:{payload['source_id']}", "object_type_code": "Document"},
                property_candidate="source.mock_payload",
                relation_candidate=None,
                value=payload,
                value_type="collection",
                evidence={"adapter": "mock", "content_type": fetched.content_type},
                confidence=0.5,
                raw_payload={"content_sha256": fetched.metadata.get("checksum")},
            )
        ]
