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
