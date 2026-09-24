"""Idempotent demo seed for Swagger and acceptance scenarios."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from typing import Any

from andromeda_core.application.knowledge_service import KnowledgeService
from andromeda_core.application.ontology_service import OntologyService
from andromeda_core.application.rule_service import RuleService
from andromeda_core.domain.identity import new_id
from andromeda_core.infrastructure.config import Settings
from andromeda_core.infrastructure.db.repositories import CoreRepository
from andromeda_core.infrastructure.db.session import create_engine, create_session_factory

UTC = UTC


async def seed_demo(database_url: str | None = None) -> dict[str, Any]:
    settings = Settings(database_url=database_url or os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./andromeda.db"))
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            repo = CoreRepository(session)
            ontology = await _ensure_ontology(repo)
            await _ensure_definitions(repo, ontology["id"])
            if ontology["status"] != "ACTIVE":
                await OntologyService(repo).activate(ontology["id"], "SEED", ontology["row_version"])
                ontology = await repo.get_ontology(ontology["id"])
            source = await KnowledgeService(repo).create_source(
                {
                    "source_type": "PDF",
                    "url": "https://example.edu/bmstu/admission-2027.pdf",
                    "external_identifier": "bmstu-admission-2027",
                    "publisher": "BMSTU",
                    "retrieved_at": datetime.now(UTC),
                    "checksum": "demo-bmstu-admission-2027",
                    "content_metadata": {"title": "BMSTU Admission Campaign 2027", "pages": 20},
                    "trust_metadata": {"publisher_verified": True},
                    "parser_version": "demo-parser-1",
                },
                "SEED",
            )
            objects = await _ensure_objects(repo, ontology["id"])
            fact = await _ensure_campaign_fact(repo, source["id"], ontology["id"], objects["program_a"], objects["campaign"])
            relation = await _ensure_relation(repo, source["id"], ontology["id"], objects["university"], objects["program_a"])
            rule_provenance = await _ensure_rule_provenance(repo, source["id"])
            base_rule = await _ensure_base_score_rule(repo, ontology["id"], objects["program_a"], rule_provenance["id"])
            rule = await _ensure_bonus_rule(repo, ontology["id"], fact["id"], rule_provenance["id"])
            benefit_rule = await _ensure_benefit_rule(repo, ontology["id"], rule_provenance["id"])
            return {
                "ontology_id": ontology["id"],
                "source_id": source["id"],
                "objects": objects,
                "fact_id": fact["id"],
                "relation_id": relation["id"],
                "rule_provenance_id": rule_provenance["id"],
                "base_rule_id": base_rule["id"],
                "bonus_rule_id": rule["id"],
                "benefit_rule_id": benefit_rule["id"],
            }
    finally:
        await engine.dispose()


async def _ensure_ontology(repo: CoreRepository) -> dict[str, Any]:
    versions = await repo.list_ontologies()
    existing = next((item for item in versions if item["version_code"] == "v1"), None)
    if existing:
        return existing
    return await OntologyService(repo).create_version({"version_code": "v1", "change_type": "BACKWARD_COMPATIBLE"}, "SEED")


async def _ensure_definitions(repo: CoreRepository, ontology_id: str) -> None:
    service = OntologyService(repo)
    current = await repo.ontology_definitions(ontology_id)
    object_types = [
        ("University", "University"),
        ("Program", "Program"),
        ("Curriculum", "Curriculum"),
        ("Subject", "Subject"),
        ("Exam", "Exam"),
        ("AdmissionCampaign", "Admission campaign"),
        ("Benefit", "Admission benefit"),
    ]
    existing_types = {item["code"] for item in current["object_types"]}
    for code, name in object_types:
        if code not in existing_types:
            await service.add_definition(ontology_id, "object_type", {"code": code, "name": name, "description": "Demo ontology object type"}, "SEED")
    current = await repo.ontology_definitions(ontology_id)
    properties = [
        {"code": "program.admission_campaign", "value_type": "reference", "allowed_object_types": ["Program"]},
        {"code": "admission.campaign_year", "value_type": "integer", "allowed_object_types": ["AdmissionCampaign"]},
        {"code": "program.base_score", "value_type": "integer", "allowed_object_types": ["Program"]},
    ]
    existing_properties = {item["code"] for item in current["properties"]}
    for definition in properties:
        if definition["code"] not in existing_properties:
            await service.add_definition(ontology_id, "property", {**definition, "description": "Demo typed property"}, "SEED")
    current = await repo.ontology_definitions(ontology_id)
    relations = [
        {"code": "OFFERS", "name": "offers", "allowed_source_types": ["University"], "allowed_target_types": ["Program"]},
        {"code": "PARTICIPATES_IN", "name": "participates in", "allowed_source_types": ["Program"], "allowed_target_types": ["AdmissionCampaign"]},
        {"code": "HAS_CURRICULUM", "name": "has curriculum", "allowed_source_types": ["Program"], "allowed_target_types": ["Curriculum"]},
        {"code": "CONTAINS", "name": "contains", "allowed_source_types": ["Curriculum"], "allowed_target_types": ["Subject"]},
        {"code": "REPLACES", "name": "replaces", "allowed_source_types": ["Benefit"], "allowed_target_types": ["Benefit"]},
    ]
    existing_relations = {item["code"] for item in current["relation_types"]}
    for relation in relations:
        if relation["code"] not in existing_relations:
            await service.add_definition(ontology_id, "relation_type", {**relation, "cardinality": "MANY_TO_MANY", "description": "Demo typed relation"}, "SEED")


async def _ensure_objects(repo: CoreRepository, ontology_id: str) -> dict[str, Any]:
    service = KnowledgeService(repo)
    values = {
        "university": ("university:bmstu", "University", "BMSTU"),
        "program_a": ("program:bmstu-ai", "Program", "Program A — Applied Informatics"),
        "program_b": ("program:bmstu-cs", "Program", "Program B — Computer Science"),
        "campaign": ("campaign:2027", "AdmissionCampaign", "Admission Campaign 2027"),
    }
    result: dict[str, Any] = {}
    for key, (stable_key, object_type, name) in values.items():
        result[key] = await service.create_object({"stable_key": stable_key, "object_type_code": object_type, "display_name": name, "properties": {}, "ontology_version_id": ontology_id}, "SEED")
    return result


async def _ensure_campaign_fact(repo: CoreRepository, source_id: str, ontology_id: str, program: dict[str, Any], campaign: dict[str, Any]) -> dict[str, Any]:
    value = campaign["id"]
    existing = next(
        (
            item
            for item in await repo.list_facts(subject_id=program["id"], property_code="program.admission_campaign")
            if item.get("value") == value
        ),
        None,
    )
    if existing:
        return existing
    observation = await KnowledgeService(repo).create_observation(
        {
            "source_id": source_id,
            "subject_candidate": {
                "stable_key": program["stable_key"],
                "object_type_code": "Program",
                "display_name": program["display_name"],
            },
            "property_candidate": "program.admission_campaign",
            "value": value,
            "value_type": "reference",
            "evidence": {"page": 4, "section": "Admission campaigns"},
            "confidence": 1,
            "confidence_status": "VERIFIED",
            "ontology_version_id": ontology_id,
            "idempotency_key": "demo-program-a-campaign-2027",
        },
        "SEED",
    )
    accepted = await KnowledgeService(repo).accept_observation(observation["id"], "SEED")
    return accepted["fact"]


async def _ensure_relation(repo: CoreRepository, source_id: str, ontology_id: str, university: dict[str, Any], program: dict[str, Any]) -> dict[str, Any]:
    existing = next((item for item in await repo.list_relations(university["id"], "OFFERS") if item["object_id"] == program["id"]), None)
    if existing:
        return existing
    provenance = await repo.create_provenance({"id": new_id(), "source_id": source_id, "observation_id": None, "evidence_locator": {"page": 3, "section": "Programs"}, "extraction_method": "demo_seed", "created_at": datetime.now(UTC)})
    return await KnowledgeService(repo).create_relation({"subject_id": university["id"], "relation_type_code": "OFFERS", "object_id": program["id"], "properties": {}, "ontology_version_id": ontology_id, "provenance_id": provenance["id"], "confidence": 1, "confidence_status": "VERIFIED"}, "SEED")


async def _ensure_rule_provenance(repo: CoreRepository, source_id: str) -> dict[str, Any]:
    existing_rule = next((item for item in await repo.list_rules() if item.get("provenance_id")), None)
    if existing_rule:
        return await repo.get_provenance(existing_rule["provenance_id"])
    return await repo.create_provenance({"id": new_id(), "source_id": source_id, "observation_id": None, "evidence_locator": {"page": 7, "section": "Admission rules"}, "extraction_method": "demo_seed", "created_at": datetime.now(UTC)})


async def _ensure_bonus_rule(repo: CoreRepository, ontology_id: str, fact_id: str, provenance_id: str) -> dict[str, Any]:
    existing = next((item for item in await repo.list_rules() if item["logical_key"] == "admission.additional_exam_bonus" and item["version"] == 1), None)
    if existing:
        return await repo.get_rule(existing["id"])
    payload = {
        "logical_key": "admission.additional_exam_bonus",
        "version": 1,
        "rule_type": "score_adjustment",
        "scope": {"program_id": "missing", "campaign_year": 2027},
        "conditions": {"kind": "logical", "operator": "and", "args": [
            {"kind": "exists", "target": {"kind": "fact", "property": "program.admission_campaign", "id": fact_id}},
            {"kind": "exists", "target": {"kind": "applicant", "path": "additional_exams"}},
            {"kind": "comparison", "operator": ">=", "left": {"kind": "applicant", "path": "scores.physics"}, "right": 90},
        ]},
        "effects": [{"type": "ADD", "target": "admission_score", "value": 30, "reason": "Declarative demo effect"}],
        "exceptions": [{"kind": "comparison", "operator": "==", "left": {"kind": "context", "path": "admission_type"}, "right": "BVI"}],
        "priority": 100,
        "ontology_version_id": ontology_id,
        "provenance_id": provenance_id,
        "test_cases": [],
    }
    program_a = next((item for item in await repo.list_objects("Program") if item["stable_key"] == "program:bmstu-ai"), None)
    payload["scope"]["program_id"] = program_a["id"] if program_a else "missing"
    payload["test_cases"] = _bonus_tests(fact_id, payload["scope"]["program_id"])
    service = RuleService(repo)
    created = await service.create(payload, "SEED")
    await service.validate(created["id"], "SEED")
    await service.test(created["id"], "SEED")
    await service.activate(created["id"], "SEED")
    return await repo.get_rule(created["id"])


async def _ensure_base_score_rule(repo: CoreRepository, ontology_id: str, program: dict[str, Any], provenance_id: str) -> dict[str, Any]:
    existing = next((item for item in await repo.list_rules() if item["logical_key"] == "score.base_from_context" and item["version"] == 1), None)
    if existing:
        return await repo.get_rule(existing["id"])
    payload = {
        "logical_key": "score.base_from_context",
        "version": 1,
        "rule_type": "score_initialization",
        "scope": {"program_id": program["id"]},
        "conditions": {"kind": "exists", "target": {"kind": "context", "path": "base_score"}},
        "effects": [{"type": "SET", "target": "admission_score", "value": {"kind": "context", "path": "base_score"}}],
        "priority": 200,
        "ontology_version_id": ontology_id,
        "provenance_id": provenance_id,
        "test_cases": [{
            "name": "base_score_is_set",
            "context": {"program_id": program["id"], "base_score": 275},
            "expected_effects": [{"type": "SET", "target": "admission_score", "value": 275}],
        }],
    }
    service = RuleService(repo)
    created = await service.create(payload, "SEED")
    await service.validate(created["id"], "SEED")
    await service.test(created["id"], "SEED")
    await service.activate(created["id"], "SEED")
    return await repo.get_rule(created["id"])


def _bonus_tests(fact_id: str, program_id: str) -> list[dict[str, Any]]:
    fact = {"id": fact_id, "property_code": "program.admission_campaign", "value": "campaign:2027"}
    context = {"program_id": program_id, "campaign_year": 2027, "base_score": 275}
    return [
        {"name": "no_additional_exam", "given_facts": [fact], "context": context, "applicant": {"scores": {"physics": 94}, "additional_exams": []}, "expected_effects": []},
        {"name": "score_89", "given_facts": [fact], "context": context, "applicant": {"scores": {"physics": 89}, "additional_exams": [{"code": "physics"}]}, "expected_effects": []},
        {"name": "score_90", "given_facts": [fact], "context": context, "applicant": {"scores": {"physics": 90}, "additional_exams": [{"code": "physics"}]}, "expected_effects": [{"type": "ADD", "target": "admission_score", "value": 30}]},
        {"name": "score_100", "given_facts": [fact], "context": context, "applicant": {"scores": {"physics": 100}, "additional_exams": [{"code": "physics"}]}, "expected_effects": [{"type": "ADD", "target": "admission_score", "value": 30}]},
        {"name": "exception_bvi", "given_facts": [fact], "context": {**context, "admission_type": "BVI"}, "applicant": {"scores": {"physics": 100}, "additional_exams": [{"code": "physics"}]}, "expected_effects": []},
    ]


async def _ensure_benefit_rule(repo: CoreRepository, ontology_id: str, provenance_id: str) -> dict[str, Any]:
    existing = next((item for item in await repo.list_rules() if item["logical_key"] == "benefit.two_of_three" and item["version"] == 1), None)
    if existing:
        return await repo.get_rule(existing["id"])
    conditions = {"kind": "quantifier", "operator": "at_least", "count": 2, "items": [
        {"kind": "comparison", "operator": "==", "left": {"kind": "applicant", "path": "additional.math_olympiad"}, "right": True},
        {"kind": "comparison", "operator": "==", "left": {"kind": "applicant", "path": "additional.research_project"}, "right": True},
        {"kind": "comparison", "operator": "==", "left": {"kind": "applicant", "path": "additional.volunteer"}, "right": True},
    ]}
    payload = {"logical_key": "benefit.two_of_three", "version": 1, "rule_type": "benefit", "scope": {}, "conditions": conditions, "effects": [{"type": "GRANT", "target": "benefit_x", "value": True}], "priority": 10, "ontology_version_id": ontology_id, "provenance_id": provenance_id, "test_cases": [{"name": "two_conditions", "applicant": {"additional": {"math_olympiad": True, "research_project": True, "volunteer": False}}, "expected_effects": [{"type": "GRANT", "target": "benefit_x", "value": True}]}]}
    service = RuleService(repo)
    created = await service.create(payload, "SEED")
    await service.validate(created["id"], "SEED")
    await service.test(created["id"], "SEED")
    await service.activate(created["id"], "SEED")
    return await repo.get_rule(created["id"])


if __name__ == "__main__":
    print(asyncio.run(seed_demo()))
