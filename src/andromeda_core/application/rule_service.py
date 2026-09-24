"""Rule lifecycle, test execution and conflict policy."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from andromeda_core.application.audit_service import record_audit
from andromeda_core.application.change_service import ChangeDetectionService
from andromeda_core.application.dependency_service import DependencyService
from andromeda_core.application.ontology_service import OntologyService
from andromeda_core.domain.common import (
    ReviewReason,
    ReviewStatus,
    RuleStatus,
    utc_now,
    validate_temporal_values,
)
from andromeda_core.domain.engine import EngineInput, RuleEngine
from andromeda_core.domain.errors import (
    ActivationError,
    ConflictError,
    RuleConflictError,
    ValidationError,
)
from andromeda_core.domain.ports.repositories import RepositoryPort
from andromeda_core.domain.rules import (
    RULE_RELATION_TYPES,
    RuleRecord,
    effect_conflicts,
    validate_rule_payload,
)


class RuleService:
    def __init__(self, repo: RepositoryPort, engine: RuleEngine | None = None, confidence_review_threshold: float = 0.8) -> None:
        self.repo = repo
        self.engine = engine or RuleEngine()
        self.confidence_review_threshold = confidence_review_threshold

    async def create_candidate(self, data: dict[str, Any], actor: str) -> dict[str, Any]:
        """Persist a rule candidate with immutable source-document provenance.

        Candidate ingestion is intentionally separate from manual rule creation:
        it can produce a draft/review item, but it never activates a rule.
        """

        idempotency_key = data.get("idempotency_key") or f"rule-candidate:{data['candidate_id']}"
        existing = await self.repo.find_rule_by_idempotency(idempotency_key)
        if existing:
            rule = await self.repo.get_rule(existing["id"])
            return await self._existing_candidate_result(rule, data["candidate_id"])

        source = await self.repo.find_source(data["source_id"])
        source_document = await self.repo.get_source_document(data["source_document_id"])
        if source_document["source_id"] != source["id"]:
            raise ValidationError(
                "SOURCE_DOCUMENT_MISMATCH",
                "Rule candidate source_document_id belongs to another source.",
                {"source_id": source["id"], "source_document_id": source_document["id"]},
            )
        ontology = await self.repo.get_ontology(str(data["ontology_version_id"])) if data.get("ontology_version_id") else await self.repo.get_active_ontology()
        if not ontology:
            raise ValidationError("NO_ACTIVE_ONTOLOGY", "An active ontology is required for a rule candidate.")
        data = {**data, "ontology_version_id": ontology["id"], "idempotency_key": idempotency_key}
        report = validate_rule_payload(data)
        if not report["valid"]:
            raise ValidationError("INVALID_RULE_CANDIDATE", "Rule candidate failed Rule DSL validation.", {"validation": report})

        provenance = await self.repo.create_provenance(
            {
                "id": str(uuid4()),
                "source_id": source["id"],
                "source_document_id": source_document["id"],
                "observation_id": None,
                "evidence_locator": {
                    "source_document_id": source_document["id"],
                    "candidate_id": data["candidate_id"],
                    "items": data.get("evidence", []),
                    "metadata": data.get("metadata", {}),
                },
                "extraction_method": "ingestion_rule_candidate",
                "created_at": utc_now(),
            }
        )
        rule = await self.create({**data, "provenance_id": provenance["id"]}, actor)
        definitions = await self.repo.ontology_definitions(ontology["id"])
        unknown_concepts = _unknown_rule_concepts(data, definitions)
        review_ids: list[str] = []
        proposal_ids: list[str] = []
        review_reasons: list[str] = []
        for concept in unknown_concepts:
            proposal = await self._create_unknown_concept_review(rule, data, concept, actor)
            review_ids.append(proposal["review_id"])
            proposal_ids.append(proposal["proposal_id"])
            review_reasons.append(ReviewReason.UNKNOWN_CONCEPT.value)
        if float(data.get("confidence", 0)) < self.confidence_review_threshold:
            review = await self._create_rule_review(
                rule,
                ReviewReason.LOW_CONFIDENCE.value,
                "Rule candidate confidence is below the configured acceptance threshold.",
                {"confidence": data.get("confidence", 0), "evidence": data.get("evidence", [])},
            )
            review_ids.append(review["id"])
            review_reasons.append(ReviewReason.LOW_CONFIDENCE.value)
        active_rules = await self.repo.active_rules()
        conflicts = [
            item for item in active_rules
            if item["logical_key"] != rule["logical_key"] and effect_conflicts(_as_rule_record(rule), _as_rule_record(item))
        ]
        if conflicts:
            review = await self._create_rule_review(
                rule,
                ReviewReason.RULE_CONFLICT.value,
                "Rule candidate conflicts with an active rule of equal priority.",
                {"conflicting_rule_ids": [item["id"] for item in conflicts]},
            )
            review_ids.append(review["id"])
            review_reasons.append(ReviewReason.RULE_CONFLICT.value)
            for conflict in conflicts:
                await self.repo.create_rule_relation(
                    {
                        "id": str(uuid4()),
                        "source_rule_id": rule["id"],
                        "relation_type": "CONFLICTS_WITH",
                        "target_rule_id": conflict["id"],
                        "created_at": utc_now(),
                    }
                )
        if review_reasons:
            rule = await self.repo.update_rule(rule["id"], {"status": RuleStatus.REVIEW.value}, rule["row_version"])
        await record_audit(
            repo=self.repo,
            actor=actor,
            action="RULE_CANDIDATE_RECEIVED",
            entity_type="rule",
            entity_id=rule["id"],
            after={"rule": rule, "review_reasons": sorted(set(review_reasons)), "source_document_id": source_document["id"]},
            source_id=source["id"],
        )
        await self.repo.commit()
        refreshed = await self.repo.get_rule(rule["id"])
        return {
            **_candidate_result(refreshed, data["candidate_id"]),
            "status": "NEEDS_REVIEW" if review_reasons else "DRAFT",
            "provenance_id": provenance["id"],
            "source_id": source["id"],
            "source_document_id": source_document["id"],
            "review_id": review_ids[0] if review_ids else None,
            "review_ids": review_ids,
            "proposal_id": proposal_ids[0] if proposal_ids else None,
            "proposal_ids": proposal_ids,
        }

    async def _create_unknown_concept_review(self, rule: dict[str, Any], data: dict[str, Any], concept: str, actor: str) -> dict[str, Any]:
        proposal = await OntologyService(self.repo).create_unknown_concept_proposal(
            concept_key=concept,
            reason="Rule candidate references a concept absent from the selected ontology.",
            source_evidence={"source_id": data["source_id"], "source_document_id": data["source_document_id"], "evidence": data.get("evidence", [])},
            confidence=float(data.get("confidence", 0)),
            actor=actor,
        )
        review = await self._create_rule_review(
            rule,
            ReviewReason.UNKNOWN_CONCEPT.value,
            f"Rule candidate references unknown ontology concept '{concept}'.",
            {"concept_key": concept, "ontology_proposal_id": proposal["proposal_id"]},
        )
        return {**proposal, "review_id": review["id"]}

    async def _create_rule_review(self, rule: dict[str, Any], reason: str, summary: str, evidence: dict[str, Any]) -> dict[str, Any]:
        existing = await self.repo.find_open_review("rule", rule["id"], reason)
        if existing:
            return existing
        now = utc_now()
        return await self.repo.create_review(
            {
                "id": str(uuid4()),
                "reason": reason,
                "status": ReviewStatus.NEEDS_REVIEW.value,
                "entity_type": "rule",
                "entity_id": rule["id"],
                "summary": summary,
                "evidence_json": evidence,
                "proposed_change_json": {"rule_id": rule["id"]},
                "decision_json": {},
                "created_at": now,
                "updated_at": now,
                "decided_at": None,
                "decided_by": None,
                "row_version": 1,
            }
        )

    async def _existing_candidate_result(self, rule: dict[str, Any], candidate_id: str) -> dict[str, Any]:
        result = _candidate_result(rule, candidate_id)
        reviews = [
            item
            for item in await self.repo.list_reviews(ReviewStatus.NEEDS_REVIEW.value)
            if item["entity_type"] == "rule" and item["entity_id"] == rule["id"]
        ]
        proposal_ids = [
            item.get("evidence_json", {}).get("ontology_proposal_id")
            for item in reviews
            if item.get("evidence_json", {}).get("ontology_proposal_id")
        ]
        result.update(
            {
                "status": "NEEDS_REVIEW" if reviews else result["status"],
                "review_id": reviews[0]["id"] if reviews else None,
                "review_ids": [item["id"] for item in reviews],
                "proposal_id": proposal_ids[0] if proposal_ids else None,
                "proposal_ids": proposal_ids,
            }
        )
        return result

    async def create(self, data: dict[str, Any], actor: str) -> dict[str, Any]:
        idempotency_key = data.get("idempotency_key")
        if idempotency_key:
            existing = await self.repo.find_rule_by_idempotency(idempotency_key)
            if existing:
                return await self.repo.get_rule(existing["id"])
        try:
            validate_temporal_values(valid_from=data.get("valid_from"), valid_to=data.get("valid_to"), transaction_from=data.get("transaction_from"), transaction_to=data.get("transaction_to"))
        except ValueError as exc:
            raise ValidationError("INVALID_TEMPORAL_INTERVAL", str(exc)) from exc
        ontology = await self.repo.get_ontology(str(data["ontology_version_id"])) if data.get("ontology_version_id") else await self.repo.get_active_ontology()
        if not ontology:
            raise ValidationError("NO_ACTIVE_ONTOLOGY", "An active ontology is required for a rule.")
        relationships = data.get("relationships", [])
        if data.get("replaces_rule_id"):
            await self.repo.get_rule(data["replaces_rule_id"])
        for relationship in relationships:
            if relationship.get("relation_type") not in RULE_RELATION_TYPES:
                raise ValidationError(
                    "INVALID_RULE_RELATION",
                    "Rule relationship type is not supported.",
                    {"relation_type": relationship.get("relation_type")},
                )
            await self.repo.get_rule(relationship["target_rule_id"])
        existing_rules = await self.repo.list_rules()
        version = data.get("version") or max((int(item["version"]) for item in existing_rules if item["logical_key"] == data["logical_key"]), default=0) + 1
        payload = {**data, "ontology_version_id": ontology["id"]}
        report = validate_rule_payload(payload)
        try:
            rule = await self.repo.create_rule(
                {
                    "id": str(uuid4()),
                    "logical_key": data["logical_key"],
                    "version": version,
                    "rule_type": data.get("rule_type", "generic"),
                    "scope_json": data.get("scope", {}),
                    "conditions_json": data["conditions"],
                    "effects_json": data["effects"],
                    "exceptions_json": data.get("exceptions", []),
                    "priority": data.get("priority", 0),
                    "valid_from": data.get("valid_from"),
                    "valid_to": data.get("valid_to"),
                    "transaction_from": utc_now(),
                    "transaction_to": None,
                    "provenance_id": data.get("provenance_id"),
                    "status": RuleStatus.DRAFT.value,
                    "ontology_version_id": ontology["id"],
                    "replaces_rule_id": data.get("replaces_rule_id"),
                    "idempotency_key": idempotency_key,
                    "validation_report": report,
                    "row_version": 1,
                    "created_at": utc_now(),
                    "updated_at": utc_now(),
                }
            )
        except ConflictError as exc:
            if exc.code != "RULE_CREATE_CONFLICT":
                raise
            if idempotency_key:
                existing = await self.repo.find_rule_by_idempotency(idempotency_key)
                if existing:
                    return await self.repo.get_rule(existing["id"])
            raise
        for test in data.get("test_cases", []):
            await self.repo.create_rule_test({"id": str(uuid4()), "rule_id": rule["id"], **test})
        if data.get("replaces_rule_id"):
            await self.repo.create_rule_relation({"id": str(uuid4()), "source_rule_id": rule["id"], "relation_type": "REPLACES", "target_rule_id": data["replaces_rule_id"], "created_at": utc_now()})
        for relationship in data.get("relationships", []):
            await self.repo.create_rule_relation({"id": str(uuid4()), "source_rule_id": rule["id"], "relation_type": relationship["relation_type"], "target_rule_id": relationship["target_rule_id"], "created_at": utc_now()})
        await self.repo.create_change(
            {
                "id": str(uuid4()),
                "classification": ChangeDetectionService.classify_rule(None, rule).value,
                "entity_type": "rule",
                "entity_id": rule["id"],
                "before_json": None,
                "after_json": rule,
                "reason": "Declarative rule proposed.",
                "created_at": utc_now(),
            }
        )
        await record_audit(repo=self.repo, actor=actor, action="RULE_PROPOSED", entity_type="rule", entity_id=rule["id"], after=rule)
        await self.repo.commit()
        return await self.repo.get_rule(rule["id"])

    async def validate(self, rule_id: str, actor: str) -> dict[str, Any]:
        rule = await self.repo.get_rule(rule_id)
        report = validate_rule_payload(_rule_payload(rule))
        status = RuleStatus.REVIEW.value if report["valid"] else RuleStatus.VALIDATING.value
        updated = await self.repo.update_rule(rule_id, {"validation_report": report, "status": status}, rule["row_version"])
        await record_audit(repo=self.repo, actor=actor, action="RULE_VALIDATED", entity_type="rule", entity_id=rule_id, before=rule, after=updated)
        await self.repo.commit()
        return {**await self.repo.get_rule(rule_id), "validation": report}

    async def test(self, rule_id: str, actor: str) -> dict[str, Any]:
        rule = await self.repo.get_rule(rule_id)
        validation = validate_rule_payload(_rule_payload(rule))
        if not validation["valid"]:
            await self.repo.update_rule(rule_id, {"validation_report": validation, "status": RuleStatus.VALIDATING.value}, rule["row_version"])
            await self.repo.commit()
            return {"rule_id": rule_id, "passed": False, "validation": validation, "tests": []}
        tests = await self.repo.list_rule_tests(rule_id)
        if not tests:
            raise ActivationError("Production rules require at least one test case.", {"rule_id": rule_id})
        outcomes = []
        for test in tests:
            result = self._run_test(rule, test)
            updated_test = await self.repo.update_rule_test(test["id"], {"passed": result["passed"], "last_error": result.get("error"), "last_run_at": utc_now()})
            outcomes.append({"id": test["id"], "name": test["name"], **result, "record": updated_test})
        passed = all(item["passed"] for item in outcomes)
        current = await self.repo.get_rule(rule_id)
        updated = await self.repo.update_rule(rule_id, {"status": RuleStatus.REVIEW.value if passed else RuleStatus.TESTING.value}, current["row_version"])
        await record_audit(repo=self.repo, actor=actor, action="RULE_TESTED", entity_type="rule", entity_id=rule_id, after={"passed": passed, "tests": outcomes})
        await self.repo.commit()
        return {"rule_id": rule_id, "passed": passed, "validation": validation, "tests": outcomes, "rule": updated}

    async def activate(self, rule_id: str, actor: str, expected_version: int | None = None) -> dict[str, Any]:
        rule = await self.repo.get_rule(rule_id)
        validation = validate_rule_payload(_rule_payload(rule))
        if not validation["valid"]:
            raise ActivationError("Rule validation failed.", {"validation": validation})
        tests = await self.repo.list_rule_tests(rule_id)
        if not rule.get("provenance_id"):
            raise ActivationError("An active rule must have provenance evidence.", {"rule_id": rule_id})
        if not tests or not all(test.get("passed") is True for test in tests):
            raise ActivationError("All rule test cases must pass before activation.", {"rule_id": rule_id})
        candidate = _as_rule_record(rule)
        active_rules = await self.repo.active_rules()
        replacement_id = rule.get("replaces_rule_id")
        same_key_active = [
            item
            for item in active_rules
            if item["id"] != rule_id
            and item["logical_key"] == rule["logical_key"]
            and item["id"] != replacement_id
        ]
        if same_key_active:
            raise ActivationError(
                "An active rule version with this logical key already exists; declare replaces_rule_id.",
                {"active_rule_ids": [item["id"] for item in same_key_active]},
            )
        conflicts = [item for item in active_rules if item["id"] != rule_id and item["id"] != rule.get("replaces_rule_id") and item["logical_key"] != rule["logical_key"] and effect_conflicts(candidate, _as_rule_record(item))]
        if conflicts:
            existing_review = await self.repo.find_open_review("rule", rule_id, ReviewReason.RULE_CONFLICT.value)
            review_id = existing_review["id"] if existing_review else str(uuid4())
            if not existing_review:
                await self.repo.create_review(
                    {
                        "id": review_id,
                        "reason": ReviewReason.RULE_CONFLICT.value,
                        "status": ReviewStatus.NEEDS_REVIEW.value,
                        "entity_type": "rule",
                        "entity_id": rule_id,
                        "summary": "Activation blocked by an equal-priority contradictory rule.",
                        "evidence_json": {"conflicting_rule_ids": [item["id"] for item in conflicts]},
                        "proposed_change_json": {"rule_id": rule_id},
                        "decision_json": {},
                        "created_at": utc_now(),
                        "updated_at": utc_now(),
                        "decided_at": None,
                        "decided_by": None,
                        "row_version": 1,
                    }
                )
            for conflict in conflicts:
                await self.repo.create_rule_relation({"id": str(uuid4()), "source_rule_id": rule_id, "relation_type": "CONFLICTS_WITH", "target_rule_id": conflict["id"], "created_at": utc_now()})
            await self.repo.commit()
            raise RuleConflictError([rule_id, *[item["id"] for item in conflicts]], review_id)
        if replacement_id:
            previous = await self.repo.get_rule(replacement_id)
            await self.repo.create_rule_relation({"id": str(uuid4()), "source_rule_id": rule_id, "relation_type": "REPLACES", "target_rule_id": replacement_id, "created_at": utc_now()})
            await self.repo.update_rule(
                replacement_id,
                {"status": RuleStatus.SUPERSEDED.value, "transaction_to": utc_now()},
                previous["row_version"],
            )
        activated = await self.repo.update_rule(rule_id, {"status": RuleStatus.ACTIVE.value}, expected_version or rule["row_version"])
        invalidation = {"invalidated_count": 0}
        if replacement_id:
            invalidation = await DependencyService(self.repo).invalidate("rule", replacement_id, "Rule version superseded.")
            await self.repo.create_change(
                {
                    "id": str(uuid4()),
                    "classification": ChangeDetectionService.classify_rule(rule, activated).value,
                    "entity_type": "rule",
                    "entity_id": rule_id,
                    "before_json": rule,
                    "after_json": activated,
                    "reason": f"Rule version activated as replacement for {replacement_id}.",
                    "created_at": utc_now(),
                }
            )
        else:
            invalidation = await DependencyService(self.repo).invalidate(
                "rule_catalog",
                rule["ontology_version_id"],
                "A new active rule changed the rule catalog.",
            )
        await record_audit(repo=self.repo, actor=actor, action="RULE_ACTIVATED", entity_type="rule", entity_id=rule_id, before=rule, after=activated, reason=f"replacement={replacement_id or 'none'}")
        await self.repo.commit()
        return {"rule": activated, "invalidation": invalidation}

    def _run_test(self, rule: dict[str, Any], test: dict[str, Any]) -> dict[str, Any]:
        facts = tuple(_normalize_fact(item) for item in test.get("given_facts", []))
        relations = tuple(test.get("given_relations", []))
        result = self.engine.evaluate(
            EngineInput(
                facts=facts,
                relations=relations,
                context=test.get("context", {}),
                applicant=test.get("applicant", {}),
                rules=(
                    {
                        **rule,
                        "status": RuleStatus.ACTIVE.value,
                    },
                ),
                ontology_version_id=rule["ontology_version_id"],
                engine_version="test",
            )
        )
        actual = _matched_effects(result.trace)
        expected = test.get("expected_effects", [])
        passed = _effect_projection(actual) == _effect_projection(expected)
        if test.get("expected_explanation") and test["expected_explanation"] not in result.explanation_summary:
            passed = False
        return {"passed": passed, "actual_effects": actual, "expected_effects": expected, "error": None if passed else "Expected effects or explanation did not match."}


def _rule_payload(rule: dict[str, Any]) -> dict[str, Any]:
    return {
        "logical_key": rule["logical_key"],
        "ontology_version_id": rule["ontology_version_id"],
        "conditions": rule["conditions_json"],
        "effects": rule["effects_json"],
        "exceptions": rule["exceptions_json"],
    }


def _as_rule_record(rule: dict[str, Any]) -> RuleRecord:
    return RuleRecord(
        id=rule["id"], logical_key=rule["logical_key"], version=rule["version"], rule_type=rule["rule_type"],
        scope=rule.get("scope_json", {}), conditions=rule["conditions_json"], effects=rule["effects_json"],
        exceptions=rule["exceptions_json"], priority=rule["priority"], valid_from=rule.get("valid_from"),
        valid_to=rule.get("valid_to"), transaction_from=rule["transaction_from"], transaction_to=rule.get("transaction_to"),
        provenance_id=rule.get("provenance_id"), status=RuleStatus(rule["status"]), ontology_version_id=rule["ontology_version_id"],
        replaces_rule_id=rule.get("replaces_rule_id"), row_version=rule.get("row_version", 1), test_cases=tuple(rule.get("test_cases", [])),
    )


def _normalize_fact(fact: dict[str, Any]) -> dict[str, Any]:
    return {**fact, "property_code": fact.get("property_code", fact.get("property")), "value": fact.get("value", fact.get("value_json"))}


def _matched_effects(trace: dict[str, Any]) -> list[dict[str, Any]]:
    for rule_trace in trace.get("rules", []):
        if rule_trace.get("status") == "MATCHED":
            effects = rule_trace.get("effects", [])
            return effects if isinstance(effects, list) else []
    return []


def _effect_projection(effects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: effect.get(key) for key in ("type", "target", "value") if key in effect} for effect in effects]


def _candidate_result(rule: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "rule_id": rule["id"],
        "status": "NEEDS_REVIEW" if rule["status"] == RuleStatus.REVIEW.value else rule["status"],
        "rule": rule,
        "provenance_id": rule.get("provenance_id"),
    }


def _unknown_rule_concepts(data: dict[str, Any], definitions: dict[str, list[dict[str, Any]]]) -> list[str]:
    known_properties = {item["code"] for item in definitions["properties"]}
    known_relations = {item["code"] for item in definitions["relation_types"]}
    known_objects = {item["code"] for item in definitions["object_types"]}
    known_any = known_properties | known_relations | known_objects
    unknown: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            kind = node.get("kind")
            if kind in {"fact", "facts", "collection"}:
                concept = node.get("property") or node.get("property_code")
                if isinstance(concept, str) and concept not in known_properties:
                    unknown.add(concept)
            if kind in {"relation", "relations"}:
                concept = node.get("relation_type") or node.get("relation_type_code")
                if isinstance(concept, str) and concept not in known_relations:
                    unknown.add(concept)
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(data.get("conditions"))
    visit(data.get("exceptions"))
    for effect in data.get("effects", []):
        target = effect.get("target") if isinstance(effect, dict) else None
        if isinstance(target, str) and target not in known_any:
            unknown.add(target)
        visit(effect)
    return sorted(unknown)
