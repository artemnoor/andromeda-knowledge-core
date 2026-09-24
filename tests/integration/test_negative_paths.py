from __future__ import annotations

from typing import Any

import httpx


async def test_security_boundary_and_negative_contracts(client: httpx.AsyncClient, seeded_app: tuple[Any, dict[str, Any]]) -> None:
    _, seed = seeded_app

    # Natural observation identity must distinguish different assertions when
    # the caller does not provide an explicit idempotency key.
    observation_base = {
        "source_id": seed["source_id"],
        "subject_candidate": {"stable_key": "program:natural-identity", "object_type_code": "Program"},
        "property_candidate": "program.admission_campaign",
        "value_type": "reference",
        "evidence": {"page": 1},
    }
    first_observation = await client.post(
        "/api/v1/observations",
        headers={"X-Role": "EDITOR"},
        json={**observation_base, "value": "campaign:2027"},
    )
    second_observation = await client.post(
        "/api/v1/observations",
        headers={"X-Role": "EDITOR"},
        json={**observation_base, "value": "campaign:2028"},
    )
    assert first_observation.status_code == 201
    assert second_observation.status_code == 201
    assert first_observation.json()["id"] != second_observation.json()["id"]

    forbidden = await client.post(f"/api/v1/rules/{seed['bonus_rule_id']}/activate")
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"

    invalid_rule = await client.post(
        "/api/v1/rules",
        headers={"X-Role": "EDITOR"},
        json={
            "logical_key": "negative.invalid-dsl",
            "conditions": {"kind": "comparison", "operator": "contains", "left": 1, "right": 2},
            "effects": [{"type": "SET", "target": "x", "value": 1}],
            "provenance_id": seed["rule_provenance_id"],
            "ontology_version_id": seed["ontology_id"],
            "test_cases": [{"name": "invalid", "expected_effects": []}],
        },
    )
    assert invalid_rule.status_code == 201
    validation = await client.post(f"/api/v1/rules/{invalid_rule.json()['id']}/validate", headers={"X-Role": "EDITOR"})
    assert validation.status_code == 200
    assert validation.json()["validation"]["valid"] is False

    missing_provenance = await client.post(
        "/api/v1/facts",
        headers={"X-Role": "EDITOR"},
        json={"subject_id": seed["objects"]["program_a"]["id"], "property_code": "program.base_score", "value": 275, "value_type": "integer"},
    )
    assert missing_provenance.status_code == 422
    assert missing_provenance.json()["error"]["code"] == "MISSING_PROVENANCE"

    invalid_interval = await client.post(
        "/api/v1/objects",
        headers={"X-Role": "EDITOR"},
        json={
            "stable_key": "program:bad-interval",
            "object_type_code": "Program",
            "display_name": "Bad interval",
            "valid_from": "2027-01-01T00:00:00Z",
            "valid_to": "2026-01-01T00:00:00Z",
        },
    )
    assert invalid_interval.status_code == 422
    assert invalid_interval.json()["error"]["code"] == "INVALID_TEMPORAL_INTERVAL"

    correlation = await client.get("/health", headers={"X-Correlation-ID": "not-a-uuid"})
    assert correlation.status_code == 200
    assert correlation.headers["X-Correlation-ID"] != "not-a-uuid"
    assert correlation.json()["correlation_id"] == correlation.headers["X-Correlation-ID"]
    metrics = await client.get("/metrics")
    assert metrics.status_code == 200
    assert "andromeda_http_requests_total" in metrics.text


async def test_openapi_and_swagger_contract(client: httpx.AsyncClient) -> None:
    docs = await client.get("/docs")
    schema = await client.get("/openapi.json")
    assert docs.status_code == 200
    assert "swagger-ui" in docs.text.lower()
    assert schema.status_code == 200
    paths = schema.json()["paths"]
    for path in (
        "/api/v1/ontology/versions",
        "/api/v1/sources",
        "/api/v1/observations",
        "/api/v1/rules/{rule_id}/activate",
        "/api/v1/semantic/evaluate",
        "/api/v1/semantic/simulate",
    ):
        assert path in paths
    assert "/metrics" not in paths
