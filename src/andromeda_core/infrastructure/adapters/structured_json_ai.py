"""Structured JSON HTTP AI adapter with an explicit ontology contract."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any

import httpx

from andromeda_core.domain.ports.ai import EvidenceRef, ExtractionContext, Proposal
from andromeda_core.infrastructure.adapters.evidence import build_evidence_locator

logger = logging.getLogger(__name__)


class StructuredJsonAIError(RuntimeError):
    """The provider returned an unusable response or transport failure."""


class StructuredJsonHttpAIAdapter:
    """Call an OpenAI-compatible structured JSON endpoint.

    The ontology is deliberately present both in the system instruction and
    as a first-class JSON field.  This protects the contract when a provider
    applies message templating or strips arbitrary metadata fields.
    """

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        base_url: str = "https://api.openai.com/v1",
        endpoint: str = "/chat/completions",
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds)
        self._owns_client = client is None
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def extract(self, *, context: ExtractionContext, content: bytes) -> Sequence[Proposal]:
        ontology_snapshot = context.ontology_for_prompt()
        ontology_json = json.dumps(ontology_snapshot, ensure_ascii=False, sort_keys=True)
        body: dict[str, Any] = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "ontology_snapshot": ontology_snapshot,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Extract only facts supported by the document. Return JSON with a proposals array. "
                        "Every proposal must use only the supplied ontology snapshot. "
                        f"Ontology snapshot (object types, properties, relations): {ontology_json}"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "source_id": context.source_id,
                            "source_url": context.source_url,
                            "item_key": context.item_key,
                            "profile": context.profile,
                            "document": content.decode("utf-8", errors="replace"),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        headers = {"accept": "application/json", "content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        logger.debug(
            "[FIX:ontology] sending ontology-constrained extraction",
            extra={
                "fix": True,
                "source_id": context.source_id,
                "ontology_object_types": len(ontology_snapshot["object_types"]),
                "ontology_properties": len(ontology_snapshot["properties"]),
                "ontology_relations": len(ontology_snapshot["relations"]),
            },
        )
        try:
            response = await self.client.post(self.endpoint, json=body, headers=headers)
            response.raise_for_status()
            response_json = response.json()
            raw_content = response_json["choices"][0]["message"]["content"]
            decoded = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
            raw_proposals = decoded.get("proposals", []) if isinstance(decoded, dict) else decoded
            if not isinstance(raw_proposals, list):
                raise StructuredJsonAIError("AI response proposals must be an array.")
            result = [self._proposal_from_provider(item, context, content) for item in raw_proposals if isinstance(item, dict)]
            logger.debug(
                "[FIX:ontology] ontology-constrained extraction completed",
                extra={"fix": True, "source_id": context.source_id, "proposal_count": len(result)},
            )
            return result
        except StructuredJsonAIError:
            raise
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            logger.exception("[FIX:ontology] structured AI extraction failed", extra={"fix": True, "source_id": context.source_id})
            raise StructuredJsonAIError("Structured AI extraction failed.") from exc

    @staticmethod
    def _proposal_from_provider(item: dict[str, Any], context: ExtractionContext, content: bytes) -> Proposal:
        evidence_items = item.get("evidence", [])
        evidence = tuple(
            EvidenceRef(
                source_id=context.source_id,
                locator=dict(value.get("locator", {})) if isinstance(value, dict) else {},
                excerpt_hash=value.get("excerpt_hash") if isinstance(value, dict) else None,
            )
            for value in evidence_items
            if isinstance(value, dict)
        )
        if not evidence:
            evidence = (
                EvidenceRef(
                    source_id=context.source_id,
                    locator=build_evidence_locator(
                        content,
                        content_type=str(context.metadata.get("content_type", "")),
                        quote=item.get("evidence_quote"),
                    ),
                ),
            )
        confidence = float(item.get("confidence", 0))
        return Proposal(
            proposal_type=str(item.get("proposal_type", "OBSERVATION_CANDIDATE")),
            payload=dict(item.get("payload", item)),
            confidence=max(0.0, min(1.0, confidence)),
            evidence=evidence,
            adapter="structured-json-http",
        )
