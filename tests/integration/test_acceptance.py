from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

EDITOR = {"X-Role": "EDITOR"}
REVIEWER = {"X-Role": "REVIEWER"}


def _applicant(score: int) -> dict[str, Any]:
    return {
        "scores": {"physics": score},
        "additional_exams": [{"code": "physics"}],
        "additional": {},
    }


def _evaluation(program_id: str, score: int, *, persist: bool = True) -> dict[str, Any]:
    return {
        "applicant": _applicant(score),
        "context": {
            "subject_id": program_id,
            "program_id": program_id,
            "campaign_year": 2027,
            "base_score": 275,
        },
        "derived_type": "admission_evaluation",
        "persist": persist,
    }


async def test_acceptance_knowledge_what_if_explain_and_rule_replacement(client: httpx.AsyncClient, seeded_app: tuple[Any, dict[str, Any]]) -> None:
    _, seed = seeded_app
    program_id = seed["objects"]["program_a"]["id"]

    assert (await client.get("/health")).status_code == 200
    assert (await client.get("/ready")).status_code == 200

    # Scenario A: source -> observation -> accepted fact, with idempotent replay.
    registered_source = await client.post(
        "/api/v1/sources",
        headers=EDITOR,
        json={
            "source_type": "IMPORT",
            "external_identifier": "acceptance-source-1",
            "publisher": "Acceptance fixture",
            "checksum": "acceptance-source-checksum",
        },
    )
    assert registered_source.status_code == 201, registered_source.text
    source_replay = await client.post(
        "/api/v1/sources",
        headers=EDITOR,
        json={
            "source_type": "IMPORT",
            "external_identifier": "acceptance-source-1",
            "publisher": "Acceptance fixture",
            "checksum": "acceptance-source-checksum",
        },
    )
    assert source_replay.status_code == 201
    assert source_replay.json()["id"] == registered_source.json()["id"]
    snapshot = await client.get("/api/v1/ontology/snapshot")
    assert snapshot.status_code == 200
    assert {"object_types", "properties", "relation_types", "rule_dsl_schema"}.issubset(snapshot.json())
    source_document_payload = {
        "source_id": registered_source.json()["id"],
        "document_checksum": "document-checksum-1",
        "title": "Acceptance source document",
        "content_metadata": {"raw_content_location": "artifact/source-document-1.bin"},
    }
    source_document = await client.post("/api/v1/source-documents", json=source_document_payload, headers=EDITOR)
    assert source_document.status_code == 201, source_document.text
    source_document_replay = await client.post("/api/v1/source-documents", json=source_document_payload, headers=EDITOR)
    assert source_document_replay.status_code == 201
    assert source_document_replay.json()["id"] == source_document.json()["id"]
    observation_payload = {
        "source_id": registered_source.json()["id"],
        "subject_candidate": {
            "stable_key": "program:observed-demo",
            "object_type_code": "Program",
            "display_name": "Observed demo program",
        },
        "property_candidate": "program.admission_campaign",
        "value": "campaign:2027",
        "value_type": "reference",
        "evidence": {"page": 14, "table": "quota"},
        "idempotency_key": "acceptance-observation-1",
    }
    first_observation = await client.post("/api/v1/observations", json=observation_payload, headers=EDITOR)
    assert first_observation.status_code == 201, first_observation.text
    second_observation = await client.post("/api/v1/observations", json=observation_payload, headers=EDITOR)
    assert second_observation.status_code == 201
    assert second_observation.json()["id"] == first_observation.json()["id"]
    accepted = await client.post(f"/api/v1/observations/{first_observation.json()['id']}/accept", headers=REVIEWER)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["fact"]["provenance_id"]

    # Scenario C/D: declarative rules compute a materialized result and explain it.
    initial = await client.post("/api/v1/semantic/evaluate", json=_evaluation(program_id, 89))
    assert initial.status_code == 200, initial.text
    assert initial.json()["value"]["scalars"]["admission_score"] == 275
    high_score = await client.post("/api/v1/semantic/evaluate", json=_evaluation(program_id, 90))
    assert high_score.status_code == 200, high_score.text
    high_result = high_score.json()
    assert high_result["value"]["scalars"]["admission_score"] == 305
    assert any(item["logical_key"] == "admission.additional_exam_bonus" for item in high_result["matched_rules"])
    explanation = await client.get(f"/api/v1/semantic/explain/{high_result['result_id']}")
    assert explanation.status_code == 200, explanation.text
    nodes = explanation.json()["nodes"]
    assert nodes and nodes[0]["kind"] == "rule"
    assert nodes[0]["children"][0]["kind"] == "fact"
    assert nodes[0]["children"][0]["children"][0]["kind"] == "observation"
    assert nodes[0]["children"][0]["children"][0]["children"][0]["kind"] == "source"
    assert nodes[0]["provenance"]["source"]["id"] == seed["source_id"]

    # Scenario F: immutable what-if overlay; no persisted applicant fact is changed.
    simulation = await client.post(
        "/api/v1/semantic/simulate",
        json={"base_context": _evaluation(program_id, 84, persist=False), "overrides": [{"property": "scores.physics", "value": 94}]},
    )
    assert simulation.status_code == 200, simulation.text
    simulation_body = simulation.json()
    assert simulation_body["before"]["value"]["scalars"]["admission_score"] == 275
    assert simulation_body["after"]["value"]["scalars"]["admission_score"] == 305
    assert simulation_body["persisted_changes"] == []

    # Scenario E and the main architectural acceptance test: threshold changes in data only.
    old_rule_response = await client.get(f"/api/v1/rules/{seed['bonus_rule_id']}")
    assert old_rule_response.status_code == 200
    old_rule_transaction_from = datetime.fromisoformat(old_rule_response.json()["transaction_from"].replace("Z", "+00:00"))
    fact = {"id": seed["fact_id"], "property_code": "program.admission_campaign", "value": "campaign:2027"}
    version_two = {
        "logical_key": "admission.additional_exam_bonus",
        "version": 2,
        "rule_type": "score_adjustment",
        "scope": {"program_id": program_id, "campaign_year": 2027},
        "conditions": {
            "kind": "logical",
            "operator": "and",
            "args": [
                {"kind": "exists", "target": {"kind": "fact", "property": "program.admission_campaign", "id": seed["fact_id"]}},
                {"kind": "exists", "target": {"kind": "applicant", "path": "additional_exams"}},
                {"kind": "comparison", "operator": ">=", "left": {"kind": "applicant", "path": "scores.physics"}, "right": 85},
            ],
        },
        "effects": [{"type": "ADD", "target": "admission_score", "value": 30}],
        "exceptions": [{"kind": "comparison", "operator": "==", "left": {"kind": "context", "path": "admission_type"}, "right": "BVI"}],
        "priority": 100,
        "ontology_version_id": seed["ontology_id"],
        "provenance_id": seed["rule_provenance_id"],
        "replaces_rule_id": seed["bonus_rule_id"],
        "test_cases": [
            {"name": "below_new_threshold", "given_facts": [fact], "context": {"program_id": program_id, "campaign_year": 2027}, "applicant": _applicant(84), "expected_effects": []},
            {"name": "at_new_threshold", "given_facts": [fact], "context": {"program_id": program_id, "campaign_year": 2027}, "applicant": _applicant(85), "expected_effects": [{"type": "ADD", "target": "admission_score", "value": 30}]},
        ],
    }
    version_two_headers = {**EDITOR, "Idempotency-Key": "acceptance-rule-version-two"}
    created = await client.post("/api/v1/rules", json=version_two, headers=version_two_headers)
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]
    new_rule_transaction_from = datetime.fromisoformat(created.json()["transaction_from"].replace("Z", "+00:00"))
    historical_known_at = old_rule_transaction_from + (new_rule_transaction_from - old_rule_transaction_from) / 2
    replayed = await client.post("/api/v1/rules", json=version_two, headers=version_two_headers)
    assert replayed.status_code == 201
    assert replayed.json()["id"] == rule_id
    assert (await client.post(f"/api/v1/rules/{rule_id}/validate", headers=EDITOR)).json()["validation"]["valid"] is True
    tested = await client.post(f"/api/v1/rules/{rule_id}/test", headers=EDITOR)
    assert tested.status_code == 200, tested.text
    assert tested.json()["passed"] is True
    activated = await client.post(f"/api/v1/rules/{rule_id}/activate", headers=REVIEWER)
    assert activated.status_code == 200, activated.text
    assert activated.json()["rule"]["status"] == "ACTIVE"

    old_result = await client.get(f"/api/v1/derived/{initial.json()['result_id']}")
    assert old_result.status_code == 200
    assert old_result.json()["status"] == "INVALIDATED"
    after_replacement = await client.post("/api/v1/semantic/evaluate", json=_evaluation(program_id, 89))
    assert after_replacement.status_code == 200, after_replacement.text
    assert after_replacement.json()["value"]["scalars"]["admission_score"] == 305
    assert any(item["version"] == 2 for item in after_replacement.json()["rule_versions"])

    historical_request = _evaluation(program_id, 89, persist=False)
    historical_request["context"]["known_at"] = historical_known_at.isoformat()
    historical = await client.post("/api/v1/semantic/evaluate", json=historical_request)
    assert historical.status_code == 200, historical.text
    assert historical.json()["value"]["scalars"]["admission_score"] == 275
    assert any(item["version"] == 1 for item in historical.json()["rule_versions"])


async def test_unknown_concept_and_conflict_enter_review_queue(client: httpx.AsyncClient, seeded_app: tuple[Any, dict[str, Any]]) -> None:
    _, seed = seeded_app

    # Scenario G: unknown ontology concept becomes proposal + review, never a silent definition.
    unknown = await client.post(
        "/api/v1/observations",
        headers=EDITOR,
        json={
            "source_id": seed["source_id"],
            "subject_candidate": {"stable_key": "program:unknown-concept", "object_type_code": "Program", "display_name": "Unknown concept program"},
            "property_candidate": "RegionalEducationalCoefficient",
            "value": 1.15,
            "value_type": "decimal",
            "evidence": {"page": 2},
            "idempotency_key": "unknown-concept-1",
        },
    )
    assert unknown.status_code == 201, unknown.text
    unknown_body = unknown.json()
    assert unknown_body["status"] == "NEEDS_REVIEW"
    assert unknown_body["proposal"]["proposal_id"]
    proposals = await client.get("/api/v1/ontology/proposals", params={"status": "PROPOSED"})
    assert any(item["id"] == unknown_body["proposal"]["proposal_id"] for item in proposals.json())
    reviews = await client.get("/api/v1/reviews", params={"status": "NEEDS_REVIEW"})
    assert any(item["reason"] == "UNKNOWN_CONCEPT" for item in reviews.json())
    unknown_review_id = unknown_body["proposal"]["review_id"]
    rejected = await client.post(
        f"/api/v1/reviews/{unknown_review_id}/reject",
        headers=REVIEWER,
        json={"reason": "The source assertion needs a controlled ontology change first."},
    )
    assert rejected.status_code == 200, rejected.text
    proposal = await client.get(f"/api/v1/ontology/proposals/{unknown_body['proposal']['proposal_id']}")
    assert proposal.status_code == 200
    assert proposal.json()["status"] == "REJECTED"

    def conflict_rule(logical_key: str, value: int) -> dict[str, Any]:
        return {
            "logical_key": logical_key,
            "version": 1,
            "scope": {},
            "conditions": {"kind": "exists", "target": {"kind": "context", "path": "conflict_flag"}},
            "effects": [{"type": "SET", "target": "conflict_value", "value": value}],
            "priority": 77,
            "ontology_version_id": seed["ontology_id"],
            "provenance_id": seed["rule_provenance_id"],
            "test_cases": [{"name": "matches", "context": {"conflict_flag": True}, "expected_effects": [{"type": "SET", "target": "conflict_value", "value": value}]}],
        }

    first = await client.post("/api/v1/rules", headers=EDITOR, json=conflict_rule("conflict.alpha", 1))
    assert first.status_code == 201, first.text
    first_id = first.json()["id"]
    assert (await client.post(f"/api/v1/rules/{first_id}/validate", headers=EDITOR)).json()["validation"]["valid"]
    assert (await client.post(f"/api/v1/rules/{first_id}/test", headers=EDITOR)).json()["passed"]
    assert (await client.post(f"/api/v1/rules/{first_id}/activate", headers=REVIEWER)).status_code == 200

    second = await client.post("/api/v1/rules", headers=EDITOR, json=conflict_rule("conflict.beta", 2))
    assert second.status_code == 201, second.text
    second_id = second.json()["id"]
    assert (await client.post(f"/api/v1/rules/{second_id}/validate", headers=EDITOR)).json()["validation"]["valid"]
    assert (await client.post(f"/api/v1/rules/{second_id}/test", headers=EDITOR)).json()["passed"]
    blocked = await client.post(f"/api/v1/rules/{second_id}/activate", headers=REVIEWER)
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["error"]["code"] == "RULE_CONFLICT"
    conflict_reviews = await client.get("/api/v1/reviews", params={"status": "NEEDS_REVIEW"})
    assert any(item["reason"] == "RULE_CONFLICT" for item in conflict_reviews.json())


async def test_rule_candidate_is_first_class_and_keeps_source_document_provenance(
    client: httpx.AsyncClient, seeded_app: tuple[Any, dict[str, Any]]
) -> None:
    _, seed = seeded_app
    source_document = await client.post(
        "/api/v1/source-documents",
        headers=EDITOR,
        json={
            "source_id": seed["source_id"],
            "document_checksum": "rule-candidate-document-1",
            "title": "Regulation candidate source",
            "content_metadata": {"page": 12},
        },
    )
    assert source_document.status_code == 201, source_document.text
    document_id = source_document.json()["id"]
    payload = {
        "candidate_id": "candidate-rule-1",
        "logical_key": "admission.unknown_benefit",
        "rule_type": "admission_benefit",
        "scope": {"campaign_year": 2027},
        "conditions": {"kind": "exists", "target": {"kind": "fact", "property": "RegionalEducationalCoefficient", "id": "candidate-fact-1"}},
        "effects": [{"type": "GRANT", "target": "benefit_x", "value": True}],
        "priority": 20,
        "confidence": "0.95",
        "confidence_status": "HIGH_CONFIDENCE",
        "evidence": [{"page": 12, "quote": "Benefit X"}],
        "source_id": seed["source_id"],
        "source_document_id": document_id,
        "ontology_version_id": seed["ontology_id"],
    }
    headers = {**EDITOR, "Idempotency-Key": "rule-candidate-1"}
    created = await client.post("/api/v1/rules/candidates", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "NEEDS_REVIEW"
    assert body["rule_id"]
    assert body["provenance_id"]
    assert body["proposal_id"]
    assert body["review_id"]
    assert body["rule"]["version"] == 1
    provenance = await client.get(f"/api/v1/provenance/{body['provenance_id']}")
    assert provenance.status_code == 200, provenance.text
    assert provenance.json()["source_document"]["id"] == document_id
    replay = await client.post("/api/v1/rules/candidates", headers=headers, json=payload)
    assert replay.status_code == 201
    assert replay.json()["rule_id"] == body["rule_id"]

    version_two_payload = {**payload, "candidate_id": "candidate-rule-2", "effects": [{"type": "SET", "target": "unknown_benefit", "value": False}]}
    second = await client.post(
        "/api/v1/rules/candidates",
        headers={**EDITOR, "Idempotency-Key": "rule-candidate-2"},
        json=version_two_payload,
    )
    assert second.status_code == 201, second.text
    assert second.json()["rule"]["version"] == 2
    versions = await client.get("/api/v1/rules", params={"status": "REVIEW"})
    assert {item["version"] for item in versions.json() if item["logical_key"] == "admission.unknown_benefit"} == {1, 2}


async def test_rule_candidate_effect_targets_are_output_channels_not_ontology_concepts(
    client: httpx.AsyncClient, seeded_app: tuple[Any, dict[str, Any]]
) -> None:
    _, seed = seeded_app
    source_document = await client.post(
        "/api/v1/source-documents",
        headers=EDITOR,
        json={
            "source_id": seed["source_id"],
            "document_checksum": "rule-candidate-derived-targets",
            "title": "Derived target regulation",
            "content_metadata": {"page": 3},
        },
    )
    assert source_document.status_code == 201, source_document.text
    document_id = source_document.json()["id"]

    def candidate(candidate_id: str, effect: dict[str, Any], *, conditions: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "candidate_id": candidate_id,
            "logical_key": f"admission.derived-target.{candidate_id}",
            "rule_type": "admission_benefit",
            "scope": {"campaign_year": 2027},
            "conditions": conditions or {"kind": "comparison", "operator": ">=", "left": {"kind": "context", "path": "campaign_year"}, "right": 2027},
            "effects": [effect],
            "confidence": "0.95",
            "confidence_status": "HIGH_CONFIDENCE",
            "evidence": [{"page": 3, "quote": "Derived outcome"}],
            "source_id": seed["source_id"],
            "source_document_id": document_id,
            "ontology_version_id": seed["ontology_id"],
        }

    add_score = await client.post(
        "/api/v1/rules/candidates",
        headers={**EDITOR, "Idempotency-Key": "derived-target-add"},
        json=candidate("derived-add", {"type": "ADD", "target": "admission_score", "value": 30}),
    )
    assert add_score.status_code == 201, add_score.text
    assert add_score.json()["status"] == "DRAFT"
    assert add_score.json()["review_id"] is None
    assert add_score.json()["proposal_id"] is None

    grant_benefit = await client.post(
        "/api/v1/rules/candidates",
        headers={**EDITOR, "Idempotency-Key": "derived-target-grant"},
        json=candidate("derived-grant", {"type": "GRANT", "target": "benefit_x", "value": True}),
    )
    assert grant_benefit.status_code == 201, grant_benefit.text
    assert grant_benefit.json()["status"] == "DRAFT"
    assert grant_benefit.json()["review_id"] is None
    assert grant_benefit.json()["proposal_id"] is None

    unknown_relation = await client.post(
        "/api/v1/rules/candidates",
        headers={**EDITOR, "Idempotency-Key": "unknown-relation-candidate"},
        json=candidate(
            "unknown-relation",
            {"type": "SET", "target": "eligibility", "value": True},
            conditions={"kind": "exists", "target": {"kind": "relation", "relation_type": "UNKNOWN_RELATION", "id": "relation-1"}},
        ),
    )
    assert unknown_relation.status_code == 201, unknown_relation.text
    assert unknown_relation.json()["status"] == "NEEDS_REVIEW"
    assert unknown_relation.json()["proposal_id"]
    assert unknown_relation.json()["review_id"]
