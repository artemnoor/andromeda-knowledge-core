"""Source, observation, object, relation and fact application use cases."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from andromeda_core.application.audit_service import record_audit
from andromeda_core.application.change_service import ChangeDetectionService
from andromeda_core.application.dependency_service import DependencyService
from andromeda_core.application.ontology_service import OntologyService
from andromeda_core.domain.common import (
    ConfidenceStatus,
    ObservationStatus,
    SourceType,
    VerificationStatus,
    utc_now,
    validate_temporal_values,
)
from andromeda_core.domain.errors import ValidationError
from andromeda_core.domain.identity import identity_hash, new_id
from andromeda_core.domain.ports.repositories import RepositoryPort


class KnowledgeService:
    def __init__(self, repo: RepositoryPort, confidence_review_threshold: float = 0.8) -> None:
        self.repo = repo
        self.ontology = OntologyService(repo)
        self.confidence_review_threshold = confidence_review_threshold

    async def create_source(self, data: dict[str, Any], actor: str) -> dict[str, Any]:
        try:
            SourceType(data["source_type"])
        except (KeyError, ValueError) as exc:
            raise ValidationError("INVALID_SOURCE_TYPE", "Source type is not supported by the source port.") from exc
        data = {**data, "url": str(data["url"]) if data.get("url") else None}
        existing = await self.repo.upsert_source({"id": new_id(), "created_at": utc_now(), **data})
        await record_audit(repo=self.repo, actor=actor, action="SOURCE_REGISTERED", entity_type="source", entity_id=existing["id"], after=existing)
        await self.repo.commit()
        return existing

    async def create_observation(self, data: dict[str, Any], actor: str) -> dict[str, Any]:
        _validate_confidence_status(data.get("confidence_status", ConfidenceStatus.UNKNOWN.value))
        source = await self.repo.find_source(data["source_id"])
        natural_identity = {
            "source_document_id": data.get("source_document_id"),
            "subject_candidate": data.get("subject_candidate", {}),
            "property_candidate": data.get("property_candidate"),
            "relation_candidate": data.get("relation_candidate"),
            "value": data.get("value"),
            "value_type": data.get("value_type"),
            "evidence": data.get("evidence", {}),
            "raw_payload": data.get("raw_payload", {}),
        }
        idempotency_key = data.get("idempotency_key") or identity_hash(source["id"], natural_identity)
        existing = await self.repo.find_observation_by_key(idempotency_key)
        if existing:
            return existing
        ontology = await self.repo.get_active_ontology()
        status = ObservationStatus.RAW.value
        proposal: dict[str, Any] | None = None
        if ontology:
            definitions = await self.repo.ontology_definitions(ontology["id"])
            property_code = data.get("property_candidate")
            if property_code and not any(item["code"] == property_code for item in definitions["properties"]):
                proposal = await self.ontology.create_unknown_concept_proposal(
                    concept_key=property_code,
                    reason="Observation references a property absent from the active ontology.",
                    source_evidence={"source_id": source["id"], "evidence": data.get("evidence", {})},
                    confidence=float(data.get("confidence", 0)),
                    actor=actor,
                )
                status = ObservationStatus.NEEDS_REVIEW.value
            else:
                status = ObservationStatus.MAPPED.value
        if float(data.get("confidence", 0)) < self.confidence_review_threshold:
            status = ObservationStatus.NEEDS_REVIEW.value
        observation = await self.repo.create_observation(
            {
                "id": new_id(),
                "source_id": source["id"],
                "source_document_id": data.get("source_document_id"),
                "status": status,
                "subject_candidate": data["subject_candidate"],
                "property_candidate": data.get("property_candidate"),
                "relation_candidate": data.get("relation_candidate"),
                "value_json": data.get("value"),
                "value_type": data.get("value_type"),
                "evidence_json": data.get("evidence", {}),
                "confidence": data.get("confidence", 0),
                "confidence_status": data.get("confidence_status", "UNKNOWN"),
                "ontology_version_id": data.get("ontology_version_id") or (ontology["id"] if ontology else None),
                "idempotency_key": idempotency_key,
                "raw_payload": data.get("raw_payload", {}),
                "created_at": utc_now(),
                "updated_at": utc_now(),
                "row_version": 1,
            }
        )
        review = None
        if status == ObservationStatus.NEEDS_REVIEW.value and proposal is None:
            review = await self.repo.create_review(
                {
                    "id": new_id(),
                    "reason": "LOW_CONFIDENCE",
                    "status": "NEEDS_REVIEW",
                    "entity_type": "observation",
                    "entity_id": observation["id"],
                    "summary": "Observation confidence is below the configured acceptance threshold.",
                    "evidence_json": data.get("evidence", {}),
                    "proposed_change_json": {"confidence": data.get("confidence", 0)},
                    "decision_json": {},
                    "created_at": utc_now(),
                    "updated_at": utc_now(),
                    "decided_at": None,
                    "decided_by": None,
                    "row_version": 1,
                }
            )
        after = {**observation, "proposal": proposal, "review": review}
        await record_audit(repo=self.repo, actor=actor, action="OBSERVATION_CREATED", entity_type="observation", entity_id=observation["id"], after=after, source_id=source["id"])
        await self.repo.commit()
        return after

    async def accept_observation(self, observation_id: str, actor: str) -> dict[str, Any]:
        observation = await self.repo.get_observation(observation_id)
        if observation["status"] == ObservationStatus.ACCEPTED.value:
            return observation
        if observation["status"] == ObservationStatus.NEEDS_REVIEW.value:
            raise ValidationError("OBSERVATION_NEEDS_REVIEW", "Observation must be reviewed before it can become a fact.")
        ontology = await self.repo.get_active_ontology()
        if not ontology:
            raise ValidationError("NO_ACTIVE_ONTOLOGY", "An active ontology is required to accept observations.")
        definitions = await self.repo.ontology_definitions(ontology["id"])
        property_code = observation.get("property_candidate")
        property_definition = next((item for item in definitions["properties"] if item["code"] == property_code), None)
        if property_definition is None:
            raise ValidationError("UNKNOWN_CONCEPT", "Observation property is not present in the active ontology.")
        if not isinstance(property_code, str):
            raise ValidationError("UNKNOWN_CONCEPT", "Observation property is required for fact acceptance.")
        candidate = observation["subject_candidate"]
        stable_key = candidate.get("stable_key")
        object_type_code = candidate.get("object_type_code")
        if not stable_key or not object_type_code:
            raise ValidationError("ONTOLOGY_MISMATCH", "Observation subject candidate needs stable_key and object_type_code.")
        if not any(item["code"] == object_type_code for item in definitions["object_types"]):
            raise ValidationError("UNKNOWN_CONCEPT", "Observation subject type is not present in the active ontology.")
        allowed_types = property_definition.get("allowed_object_types") or []
        if allowed_types and object_type_code not in allowed_types:
            raise ValidationError("ONTOLOGY_MISMATCH", "Observation property is not allowed for the candidate object type.")
        value_type = observation.get("value_type") or property_definition["value_type"]
        _validate_typed_value(value_type, observation["value_json"], property_definition.get("enum_values"))
        subject = await self.repo.find_object_by_key(stable_key)
        if not subject:
            subject = await self.repo.upsert_object(
                {
                    "id": new_id(),
                    "stable_key": stable_key,
                    "object_type_code": object_type_code,
                    "display_name": candidate.get("display_name", stable_key),
                    "properties_json": candidate.get("properties", {}),
                    "ontology_version_id": ontology["id"],
                    "lifecycle_status": "ACTIVE",
                    "valid_from": None,
                    "valid_to": None,
                    "transaction_from": utc_now(),
                    "transaction_to": None,
                    "created_at": utc_now(),
                    "updated_at": utc_now(),
                    "row_version": 1,
                }
            )
        provenance = await self.repo.create_provenance(
            {
                "id": new_id(),
                "source_id": observation["source_id"],
                "observation_id": observation_id,
                "evidence_locator": observation["evidence_json"],
                "extraction_method": "observation_acceptance",
                "created_at": utc_now(),
            }
        )
        identity_key = identity_hash(subject["id"], property_code, json.dumps(observation["value_json"], sort_keys=True, default=str), None)
        fact = await self.repo.find_fact_by_identity(identity_key)
        if not fact:
            current_facts = await self.repo.list_facts(subject_id=subject["id"], property_code=property_code)
            before = _find_replaced_fact(current_facts, observation["value_json"], None)
            transaction_time = utc_now()
            if before:
                await self.repo.close_fact_transaction(before["id"], transaction_time)
                await DependencyService(self.repo).invalidate("fact", before["id"], "Canonical fact corrected by a newer observation.")
            fact = await self.repo.create_fact(
                {
                    "id": new_id(),
                    "subject_id": subject["id"],
                    "property_code": property_code,
                    "value": observation["value_json"],
                    "value_type": value_type,
                    "valid_from": None,
                    "valid_to": None,
                    "transaction_from": transaction_time,
                    "transaction_to": None,
                    "provenance_id": provenance["id"],
                    "confidence": observation["confidence"],
                    "confidence_status": observation["confidence_status"],
                    "verification_status": VerificationStatus.VERIFIED.value,
                    "ontology_version_id": ontology["id"],
                    "identity_key": identity_key,
                    "created_at": transaction_time,
                }
            )
        else:
            before = None
        accepted = await self.repo.update_observation(observation_id, {"status": ObservationStatus.ACCEPTED.value})
        await self.repo.create_change(
            {
                "id": new_id(),
                "classification": ChangeDetectionService.classify_fact(before, fact).value,
                "entity_type": "fact",
                "entity_id": fact["id"],
                "before_json": before,
                "after_json": fact,
                "reason": "Observation accepted as canonical fact.",
                "created_at": utc_now(),
            }
        )
        await _invalidate_fact_property_dependencies(self.repo, property_code)
        await record_audit(repo=self.repo, actor=actor, action="FACT_ACCEPTED", entity_type="fact", entity_id=fact["id"], after=fact, source_id=observation["source_id"])
        await self.repo.commit()
        return {"observation": accepted, "fact": fact, "provenance": provenance}

    async def create_object(self, data: dict[str, Any], actor: str) -> dict[str, Any]:
        _ensure_temporal(data)
        ontology = await self.repo.get_ontology(str(data["ontology_version_id"])) if data.get("ontology_version_id") else await self.repo.get_active_ontology()
        if not ontology:
            raise ValidationError("NO_ACTIVE_ONTOLOGY", "An active ontology is required.")
        definitions = await self.repo.ontology_definitions(ontology["id"])
        if not any(item["code"] == data["object_type_code"] for item in definitions["object_types"]):
            raise ValidationError("ONTOLOGY_MISMATCH", "Object type is not defined by the selected ontology.")
        result = await self.repo.upsert_object(
            {
                "id": new_id(),
                "stable_key": data["stable_key"],
                "object_type_code": data["object_type_code"],
                "display_name": data["display_name"],
                "properties_json": data.get("properties", {}),
                "ontology_version_id": ontology["id"],
                "lifecycle_status": "ACTIVE",
                "valid_from": data.get("valid_from"),
                "valid_to": data.get("valid_to"),
                "transaction_from": utc_now(),
                "transaction_to": None,
                "created_at": utc_now(),
                "updated_at": utc_now(),
                "row_version": 1,
            }
        )
        await record_audit(repo=self.repo, actor=actor, action="OBJECT_UPSERTED", entity_type="object", entity_id=result["id"], after=result)
        await self.repo.commit()
        return result

    async def create_relation(self, data: dict[str, Any], actor: str) -> dict[str, Any]:
        _ensure_temporal(data)
        _validate_confidence_status(data.get("confidence_status", ConfidenceStatus.UNKNOWN.value))
        subject = await self.repo.find_object(data["subject_id"])
        target = await self.repo.find_object(data["object_id"])
        ontology = await self.repo.get_ontology(str(data["ontology_version_id"])) if data.get("ontology_version_id") else await self.repo.get_active_ontology()
        if not ontology:
            raise ValidationError("NO_ACTIVE_ONTOLOGY", "An active ontology is required.")
        definitions = await self.repo.ontology_definitions(ontology["id"])
        relation_type = next((item for item in definitions["relation_types"] if item["code"] == data["relation_type_code"]), None)
        if not relation_type or (relation_type["allowed_source_types"] and subject["object_type_code"] not in relation_type["allowed_source_types"]) or (relation_type["allowed_target_types"] and target["object_type_code"] not in relation_type["allowed_target_types"]):
            raise ValidationError("INVALID_RELATION", "Relation type does not allow the supplied object types.")
        provenance_id = data.get("provenance_id")
        if not provenance_id:
            raise ValidationError("MISSING_PROVENANCE", "Relations require provenance.")
        identity_key = identity_hash(subject["id"], data["relation_type_code"], target["id"], data.get("valid_from"))
        existing = await self.repo.find_relation_by_identity(identity_key)
        if existing:
            return existing
        relation = await self.repo.create_relation(
            {
                "id": new_id(),
                "subject_id": subject["id"],
                "relation_type_code": data["relation_type_code"],
                "object_id": target["id"],
                "properties_json": data.get("properties", {}),
                "valid_from": data.get("valid_from"),
                "valid_to": data.get("valid_to"),
                "transaction_from": utc_now(),
                "transaction_to": None,
                "provenance_id": provenance_id,
                "confidence": data.get("confidence", 1),
                "confidence_status": data.get("confidence_status", "VERIFIED"),
                "verification_status": VerificationStatus.VERIFIED.value,
                "ontology_version_id": ontology["id"],
                "identity_key": identity_key,
                "created_at": utc_now(),
            }
        )
        await self.repo.create_change(
            {
                "id": new_id(),
                "classification": ChangeDetectionService.classify_relation(None, relation).value,
                "entity_type": "relation",
                "entity_id": relation["id"],
                "before_json": None,
                "after_json": relation,
                "reason": "Typed relation accepted by an authorized actor.",
                "created_at": utc_now(),
            }
        )
        await DependencyService(self.repo).invalidate(
            "relation_type",
            data["relation_type_code"],
            "A relation for a previously queried predicate was accepted.",
        )
        await record_audit(repo=self.repo, actor=actor, action="RELATION_ACCEPTED", entity_type="relation", entity_id=relation["id"], after=relation)
        await self.repo.commit()
        return relation

    async def create_fact(self, data: dict[str, Any], actor: str) -> dict[str, Any]:
        _ensure_temporal(data)
        _validate_confidence_status(data.get("confidence_status", ConfidenceStatus.UNKNOWN.value))
        try:
            VerificationStatus(data.get("verification_status", VerificationStatus.VERIFIED.value))
        except ValueError as exc:
            raise ValidationError("INVALID_VERIFICATION_STATUS", "Verification status is not supported.") from exc
        ontology = await self.repo.get_ontology(str(data["ontology_version_id"])) if data.get("ontology_version_id") else await self.repo.get_active_ontology()
        if not ontology:
            raise ValidationError("NO_ACTIVE_ONTOLOGY", "An active ontology is required.")
        definitions = await self.repo.ontology_definitions(ontology["id"])
        property_definition = next((item for item in definitions["properties"] if item["code"] == data["property_code"]), None)
        if property_definition is None:
            raise ValidationError("ONTOLOGY_MISMATCH", "Fact property is not defined by the selected ontology.")
        subject = await self.repo.find_object(data["subject_id"])
        allowed_types = property_definition.get("allowed_object_types") or []
        if allowed_types and subject["object_type_code"] not in allowed_types:
            raise ValidationError("ONTOLOGY_MISMATCH", "Fact property is not allowed for the supplied object type.")
        value_type = data.get("value_type") or property_definition["value_type"]
        if data.get("value_type") and data["value_type"] != property_definition["value_type"]:
            raise ValidationError("FACT_TYPE_MISMATCH", "Fact value type does not match the ontology property definition.", {"expected": property_definition["value_type"], "actual": data["value_type"]})
        _validate_typed_value(value_type, data.get("value"), property_definition.get("enum_values"))
        data = {**data, "value_type": value_type}
        provenance_id = data.get("provenance_id")
        if not provenance_id:
            if not data.get("source_id"):
                raise ValidationError("MISSING_PROVENANCE", "Facts require provenance_id or source_id.")
            provenance = await self.repo.create_provenance({"id": new_id(), "source_id": data["source_id"], "observation_id": None, "evidence_locator": {"mode": "direct_admin"}, "extraction_method": "manual", "created_at": utc_now()})
            provenance_id = provenance["id"]
        identity_key = identity_hash(data["subject_id"], data["property_code"], json.dumps(data["value"], sort_keys=True, default=str), data.get("valid_from"))
        existing = await self.repo.find_fact_by_identity(identity_key)
        if existing:
            return existing
        current_facts = await self.repo.list_facts(subject_id=data["subject_id"], property_code=data["property_code"])
        before = _find_replaced_fact(current_facts, data["value"], data.get("valid_from"))
        transaction_time = utc_now()
        if before:
            await self.repo.close_fact_transaction(before["id"], transaction_time)
            await DependencyService(self.repo).invalidate("fact", before["id"], "Canonical fact corrected by an authorized actor.")
        fact = await self.repo.create_fact({**data, "id": new_id(), "provenance_id": provenance_id, "ontology_version_id": ontology["id"], "identity_key": identity_key, "transaction_from": transaction_time, "transaction_to": None, "created_at": transaction_time})
        await self.repo.create_change({"id": new_id(), "classification": ChangeDetectionService.classify_fact(before, fact).value, "entity_type": "fact", "entity_id": fact["id"], "before_json": before, "after_json": fact, "reason": "Direct fact accepted by an authorized actor.", "created_at": utc_now()})
        await _invalidate_fact_property_dependencies(self.repo, data["property_code"])
        await record_audit(repo=self.repo, actor=actor, action="FACT_ACCEPTED", entity_type="fact", entity_id=fact["id"], after=fact, source_id=data.get("source_id"))
        await self.repo.commit()
        return fact


def _ensure_temporal(data: dict[str, Any]) -> None:
    try:
        validate_temporal_values(
            valid_from=data.get("valid_from"),
            valid_to=data.get("valid_to"),
            transaction_from=data.get("transaction_from"),
            transaction_to=data.get("transaction_to"),
        )
    except ValueError as exc:
        raise ValidationError("INVALID_TEMPORAL_INTERVAL", str(exc)) from exc


async def _invalidate_fact_property_dependencies(repo: RepositoryPort, property_code: str) -> None:
    service = DependencyService(repo)
    for selector in _fact_property_selectors(property_code):
        await service.invalidate(
            "fact_property",
            selector,
            "A canonical fact for a previously queried property was accepted.",
        )


def _fact_property_selectors(property_code: str) -> set[str]:
    parts = property_code.split(".")
    return {property_code, *{".".join(parts[:index]) + ".*" for index in range(1, len(parts))}}


def _validate_typed_value(value_type: str, value: Any, enum_values: list[str] | None = None) -> None:
    valid = (
        (value_type == "string" and isinstance(value, str))
        or (value_type == "integer" and isinstance(value, int) and not isinstance(value, bool))
        or (value_type == "decimal" and isinstance(value, (int, float, Decimal)) and not isinstance(value, bool))
        or (value_type == "boolean" and isinstance(value, bool))
        or (value_type in {"date", "datetime", "reference"} and isinstance(value, (str, datetime)))
        or (value_type == "collection" and isinstance(value, list))
        or (value_type == "enum" and isinstance(value, str) and (not enum_values or value in enum_values))
    )
    if not valid:
        raise ValidationError("FACT_TYPE_MISMATCH", "Fact value does not match the ontology type.", {"value_type": value_type})


def _validate_confidence_status(value: str) -> None:
    try:
        ConfidenceStatus(value)
    except ValueError as exc:
        raise ValidationError("INVALID_CONFIDENCE_STATUS", "Confidence status is not supported.") from exc


def _find_replaced_fact(
    facts: list[dict[str, Any]],
    value: Any,
    valid_from: datetime | None,
) -> dict[str, Any] | None:
    serialized_value = json.dumps(value, sort_keys=True, default=str)
    for fact in facts:
        if not _same_moment(fact.get("valid_from"), valid_from):
            continue
        if json.dumps(fact.get("value"), sort_keys=True, default=str) != serialized_value:
            return fact
    return None


def _same_moment(left: Any, right: datetime | None) -> bool:
    if left is None or right is None:
        return left is None and right is None
    if not isinstance(left, datetime):
        return False
    left_utc = left.replace(tzinfo=UTC) if left.tzinfo is None else left.astimezone(UTC)
    right_utc = right.replace(tzinfo=UTC) if right.tzinfo is None else right.astimezone(UTC)
    return left_utc == right_utc
