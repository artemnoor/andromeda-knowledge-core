from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from andromeda_core.application.knowledge_service import KnowledgeService
from andromeda_core.infrastructure.db.repositories import CoreRepository


@pytest.mark.asyncio
async def test_fact_valid_time_and_transaction_time_are_independent(seeded_app: tuple[Any, dict[str, Any]]) -> None:
    app, seed = seeded_app
    async with app.state.session_factory() as session:
        repository = CoreRepository(session)
        fact = await KnowledgeService(repository).create_fact(
            {
                "subject_id": seed["objects"]["program_a"]["id"],
                "property_code": "program.base_score",
                "value": 275,
                "value_type": "integer",
                "valid_from": datetime(2027, 1, 1, tzinfo=UTC),
                "valid_to": datetime(2028, 1, 1, tzinfo=UTC),
                "source_id": seed["source_id"],
                "confidence": 1,
                "verification_status": "VERIFIED",
                "confidence_status": "VERIFIED",
                "ontology_version_id": seed["ontology_id"],
            },
            "EDITOR",
        )
        before_transaction = fact["transaction_from"] - timedelta(seconds=1)
        assert not await repository.list_facts(subject_id=fact["subject_id"], property_code=fact["property_code"], valid_at=datetime(2027, 6, 1, tzinfo=UTC), known_at=before_transaction)
        assert await repository.list_facts(subject_id=fact["subject_id"], property_code=fact["property_code"], valid_at=datetime(2027, 6, 1, tzinfo=UTC), known_at=fact["transaction_from"] + timedelta(seconds=1))
        assert not await repository.list_facts(subject_id=fact["subject_id"], property_code=fact["property_code"], valid_at=datetime(2026, 6, 1, tzinfo=UTC), known_at=fact["transaction_from"] + timedelta(seconds=1))


@pytest.mark.asyncio
async def test_fact_correction_closes_current_transaction_version(seeded_app: tuple[Any, dict[str, Any]]) -> None:
    app, seed = seeded_app
    async with app.state.session_factory() as session:
        repository = CoreRepository(session)
        service = KnowledgeService(repository)
        interval_start = datetime(2029, 1, 1, tzinfo=UTC)
        first = await service.create_fact(
            {
                "subject_id": seed["objects"]["program_a"]["id"],
                "property_code": "program.base_score",
                "value": 275,
                "value_type": "integer",
                "valid_from": interval_start,
                "source_id": seed["source_id"],
                "ontology_version_id": seed["ontology_id"],
            },
            "EDITOR",
        )
        second = await service.create_fact(
            {
                "subject_id": seed["objects"]["program_a"]["id"],
                "property_code": "program.base_score",
                "value": 280,
                "value_type": "integer",
                "valid_from": interval_start,
                "source_id": seed["source_id"],
                "ontology_version_id": seed["ontology_id"],
            },
            "EDITOR",
        )
        current = await repository.list_facts(subject_id=first["subject_id"], property_code="program.base_score")
        assert [item["id"] for item in current] == [second["id"]]
        historical = await repository.list_facts(
            subject_id=first["subject_id"],
            property_code="program.base_score",
            known_at=second["transaction_from"] - timedelta(microseconds=1),
        )
        assert any(item["id"] == first["id"] for item in historical)
        changes = await repository.list_changes("FACT_CHANGED")
        assert any(item["entity_id"] == second["id"] and item["before_json"]["id"] == first["id"] for item in changes)


@pytest.mark.asyncio
async def test_ingestion_pipeline_store_persists_document_and_extraction_for_retry(seeded_app: tuple[Any, dict[str, Any]]) -> None:
    app, seed = seeded_app
    async with app.state.session_factory() as session:
        repository = CoreRepository(session)
        row = await repository.create_pipeline(
            {
                "id": "pipeline-persistence-test",
                "pipeline_key": "pipeline-key",
                "source_id": seed["source_id"],
                "source_url": "https://example.edu/admission.html",
                "item_key": "admission",
                "profile": "education-v1",
                "document_checksum": "checksum-1",
                "status": "EXTRACTED",
                "last_successful_stage": "EXTRACT",
                "failed_stage": None,
                "fetched_content": b"document",
                "content_type": "text/html",
                "fetch_metadata_json": {"status_code": 200},
                "extraction_json": [{"proposal_type": "OBSERVATION_CANDIDATE", "payload": {"value": 1}}],
                "publish_result_json": {},
                "last_error": None,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "last_run_at": datetime.now(UTC),
            }
        )
        latest = await repository.find_latest_pipeline("pipeline-key")

        assert row["id"] == "pipeline-persistence-test"
        assert latest is not None
        assert latest["fetched_content"] == b"document"
        assert latest["extraction_json"][0]["payload"]["value"] == 1
