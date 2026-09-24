"""Expand a derived trace through rules, facts, observations and sources."""

from __future__ import annotations

from typing import Any

from andromeda_core.domain.ports.repositories import RepositoryPort


class ExplainService:
    def __init__(self, repo: RepositoryPort) -> None:
        self.repo = repo

    async def explain(self, result_id: str) -> dict[str, Any]:
        derived = await self.repo.get_derived(result_id)
        trace = derived.get("trace_json", {})
        children: list[dict[str, Any]] = []
        for rule in trace.get("matched_rules", []):
            rule_id = rule.get("id")
            if not rule_id:
                continue
            rule_record = await self.repo.get_rule(rule_id)
            rule_node = {"id": rule_id, "kind": "rule", "label": f"{rule_record['logical_key']} v{rule_record['version']}", "status": rule_record["status"], "children": []}
            if rule_record.get("provenance_id"):
                rule_node["provenance"] = await self.repo.explain_provenance(rule_record["provenance_id"])
            for kind, entity_id in trace.get("dependencies", []):
                if kind == "fact":
                    fact = await self.repo.explain_fact(entity_id)
                    observation = fact.get("observation")
                    provenance = fact.get("provenance", {})
                    observation_node = {
                        "id": observation["id"] if observation else provenance.get("id"),
                        "kind": "observation" if observation else "provenance",
                        "label": "Observation" if observation else "Direct provenance",
                        "children": [
                            {
                                "id": fact["source"]["id"],
                                "kind": "source",
                                "label": fact["source"].get("url") or fact["source"].get("external_identifier"),
                                "evidence": provenance.get("evidence_locator", {}),
                            }
                        ],
                    }
                    rule_node["children"].append(
                        {
                            "id": entity_id,
                            "kind": "fact",
                            "label": f"{fact['fact']['property_code']} = {fact['fact']['value']}",
                            "confidence": fact["fact"].get("confidence"),
                            "children": [observation_node],
                        }
                    )
                elif kind == "relation":
                    relation = await self.repo.get_relation(entity_id)
                    relation_node: dict[str, Any] = {
                        "id": entity_id,
                        "kind": "relation",
                        "label": relation["relation_type_code"],
                    }
                    if relation.get("provenance_id"):
                        relation_node["provenance"] = await self.repo.explain_provenance(relation["provenance_id"])
                    rule_node["children"].append(relation_node)
            children.append(rule_node)
        return {
            "result": {"id": derived["id"], "kind": "derived", "type": derived["derived_type"], "value": derived["value_json"], "status": derived["status"]},
            "explanation": trace.get("explanation_summary", ""),
            "nodes": children,
            "metadata": {"engine_version": derived["engine_version"], "ontology_version_id": derived["ontology_version_id"], "computed_at": derived["computed_at"]},
        }
