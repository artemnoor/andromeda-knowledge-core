"""Materialized deterministic computation use case."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from andromeda_core.application.audit_service import record_audit
from andromeda_core.application.dependency_service import DependencyService
from andromeda_core.domain.common import DerivedStatus, utc_now
from andromeda_core.domain.dsl.ast import canonical_hash
from andromeda_core.domain.engine import EngineInput, EngineResult, RuleEngine
from andromeda_core.domain.ports.repositories import RepositoryPort


class ComputationService:
    def __init__(self, repo: RepositoryPort, engine: RuleEngine | None = None, engine_version: str = "engine-0.1.0") -> None:
        self.repo = repo
        self.engine = engine or RuleEngine()
        self.engine_version = engine_version

    async def evaluate(
        self,
        *,
        applicant: dict[str, Any],
        context: dict[str, Any],
        derived_type: str,
        persist: bool,
    ) -> dict[str, Any]:
        ontology = await self.repo.get_active_ontology()
        if not ontology:
            return {"derived_type": derived_type, "value": {}, "matched_rules": [], "explanation_summary": "No active ontology is available.", "persisted": False}
        valid_at = _parse_datetime(context.get("valid_at"))
        known_at = _parse_datetime(context.get("known_at"))
        rules = tuple(await self.repo.active_rules(valid_at=valid_at, known_at=known_at))
        facts = tuple(await self.repo.list_facts(subject_id=context.get("subject_id"), valid_at=valid_at, known_at=known_at))
        relations = tuple(await self.repo.list_relations(subject_id=context.get("subject_id"), valid_at=valid_at, known_at=known_at))
        ontology_definitions = await self.repo.ontology_definitions(ontology["id"])
        safe_applicant = _json_safe(deepcopy(applicant))
        safe_context = _json_safe(deepcopy(context))
        result_key = canonical_hash(
            {
                "derived_type": derived_type,
                "applicant": safe_applicant,
                "context": safe_context,
                "ontology": ontology["id"],
                "rules": [{"id": rule["id"], "version": rule["version"]} for rule in rules],
                "engine": self.engine_version,
            }
        )
        existing = await self.repo.find_derived_by_key(result_key)
        if existing and existing["status"] == DerivedStatus.VALID.value and persist:
            return _derived_response(existing, cached=True)
        engine_result = self.engine.evaluate(
            EngineInput(
                facts=facts,
                relations=relations,
                context=safe_context,
                applicant=safe_applicant,
                rules=rules,
                ontology_version_id=ontology["id"],
                engine_version=self.engine_version,
                ontology=ontology_definitions,
            )
        )
        response = _engine_response(engine_result, derived_type)
        if not persist:
            response["persisted"] = False
            return response
        data = {
            "derived_type": derived_type,
            "value_json": _json_safe(engine_result.value),
            "context_json": safe_applicant,
            "query_context_json": safe_context,
            "status": DerivedStatus.VALID.value,
            "invalidation_reason": None,
            "computed_at": utc_now(),
            "engine_version": self.engine_version,
            "ontology_version_id": ontology["id"],
            "rule_versions_json": _json_safe(engine_result.rule_versions),
            "trace_json": _json_safe(
                {
                    **engine_result.trace,
                    "explanation_summary": engine_result.explanation_summary,
                    "dependencies": sorted(engine_result.dependencies),
                    "instrumentation": {
                        "affected_nodes": sorted(engine_result.dependencies),
                        "invalidated_nodes": [],
                        "recomputed_nodes": [],
                        "duration_ms": engine_result.duration_ms,
                    },
                }
            ),
            "result_key": result_key,
            "created_at": existing["created_at"] if existing else utc_now(),
            "updated_at": utc_now(),
            "row_version": (existing["row_version"] + 1) if existing else 1,
        }
        if existing:
            materialized = await self.repo.update_derived(existing["id"], data)
        else:
            materialized = await self.repo.create_derived({"id": str(uuid4()), **data})
        for kind, entity_id in sorted(engine_result.dependencies):
            await self._add_dependency_if_missing(kind, entity_id, "derived", materialized["id"], "SUPPORTS")
        for rule in engine_result.rule_versions:
            await self._add_dependency_if_missing("rule", rule["id"], "derived", materialized["id"], "EXECUTES")
        await self._add_dependency_if_missing("ontology", ontology["id"], "derived", materialized["id"], "INTERPRETS")
        await self._add_dependency_if_missing("rule_catalog", ontology["id"], "derived", materialized["id"], "EVALUATES")
        await record_audit(repo=self.repo, actor="SYSTEM", action="DERIVED_RECOMPUTED", entity_type="derived", entity_id=materialized["id"], after={"duration_ms": engine_result.duration_ms, "dependency_count": len(engine_result.dependencies)})
        await self.repo.commit()
        persisted_response = _derived_response(materialized, cached=False)
        persisted_response["instrumentation"] = {
            "affected_nodes": sorted(engine_result.dependencies),
            "invalidated_nodes": [],
            "recomputed_nodes": [materialized["id"]],
            "duration_ms": engine_result.duration_ms,
        }
        return {**persisted_response, "persisted": True}

    async def _add_dependency_if_missing(self, source_kind: str, source_id: str, target_kind: str, target_id: str, dependency_type: str) -> None:
        existing = await self.repo.dependencies_to(target_kind, target_id)
        if any(item["source_kind"] == source_kind and item["source_id"] == source_id and item["dependency_type"] == dependency_type for item in existing):
            return
        await DependencyService(self.repo).register_edge(
            source_kind,
            source_id,
            target_kind,
            target_id,
            dependency_type,
        )


def _engine_response(result: EngineResult, derived_type: str) -> dict[str, Any]:
    return {
        "result_id": None,
        "derived_type": derived_type,
        "value": _json_safe(result.value),
        "matched_rules": result.matched_rules,
        "explanation_summary": result.explanation_summary,
        "trace": _json_safe(result.trace),
        "rule_versions": _json_safe(result.rule_versions),
        "duration_ms": result.duration_ms,
        "instrumentation": {
            "affected_nodes": sorted(result.dependencies),
            "invalidated_nodes": [],
            "recomputed_nodes": [],
            "duration_ms": result.duration_ms,
        },
    }


def _derived_response(derived: dict[str, Any], cached: bool) -> dict[str, Any]:
    trace = derived.get("trace_json", {})
    return {
        "result_id": derived["id"],
        "derived_type": derived["derived_type"],
        "value": derived["value_json"],
        "matched_rules": trace.get("matched_rules", []),
        "explanation_summary": trace.get("explanation_summary", ""),
        "trace": trace,
        "rule_versions": derived.get("rule_versions_json", []),
        "duration_ms": trace.get("instrumentation", {}).get("duration_ms", trace.get("duration_ms", 0)),
        "computed_at": derived.get("computed_at"),
        "engine_version": derived.get("engine_version"),
        "ontology_version_id": derived.get("ontology_version_id"),
        "cached": cached,
        "persisted": True,
        "instrumentation": trace.get(
            "instrumentation",
            {"affected_nodes": [], "invalidated_nodes": [], "recomputed_nodes": [], "duration_ms": 0},
        ),
    }


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str, ensure_ascii=False))


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None
