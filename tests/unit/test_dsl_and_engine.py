from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from andromeda_core.domain.dsl.evaluator import EvaluationData, evaluate
from andromeda_core.domain.engine import EngineInput, RuleEngine


def test_comparison_and_quantifier_operators() -> None:
    data = EvaluationData(
        facts=({"id": "f1", "property_code": "exam.math.score", "value": 96},),
        context={"base_score": 275},
        applicant={"scores": {"physics": 94}, "additional_exams": [{"code": "physics"}, {"code": "cs"}]},
    )
    condition = {
        "kind": "logical",
        "operator": "and",
        "args": [
            {"kind": "comparison", "operator": ">=", "left": {"kind": "applicant", "path": "scores.physics"}, "right": 90},
            {"kind": "comparison", "operator": "==", "left": {"kind": "aggregation", "operator": "count", "target": {"kind": "facts", "property": "exam.*"}}, "right": 1},
            {"kind": "quantifier", "operator": "at_least", "count": 2, "items": [
                {"kind": "exists", "target": {"kind": "applicant", "path": "scores.physics"}},
                {"kind": "exists", "target": {"kind": "applicant", "path": "additional_exams"}},
            ]},
        ],
    }
    result = evaluate(condition, data)
    assert result.value is True
    assert ("fact", "f1") in result.dependencies
    assert ("fact_property", "exam.*") in result.dependencies


def test_empty_fact_and_relation_queries_keep_selector_dependencies() -> None:
    data = EvaluationData()
    fact_result = evaluate({"kind": "exists", "target": {"kind": "fact", "property": "quota.value"}}, data)
    relation_result = evaluate({"kind": "exists", "target": {"kind": "relation", "relation_type": "OFFERS"}}, data)
    assert ("fact_property", "quota.value") in fact_result.dependencies
    assert ("relation_type", "OFFERS") in relation_result.dependencies


def test_engine_is_generic_and_deterministic() -> None:
    rule = {
        "id": "rule-1",
        "logical_key": "generic.threshold",
        "version": 1,
        "status": "ACTIVE",
        "priority": 1,
        "scope_json": {},
        "conditions_json": {"kind": "comparison", "operator": ">=", "left": {"kind": "applicant", "path": "score"}, "right": 90},
        "effects_json": [{"type": "ADD", "target": "total", "value": 30}],
        "exceptions_json": [],
    }
    input_data = EngineInput(facts=(), relations=(), context={"base_score": 275}, applicant={"score": 94}, rules=(rule,), ontology_version_id="o1", engine_version="e1")
    first = RuleEngine().evaluate(input_data)
    second = RuleEngine().evaluate(input_data)
    assert first.value["scalars"]["total"] == 30
    assert first.canonical_hash() == second.canonical_hash()


@given(st.integers(min_value=0, max_value=200))
def test_threshold_evaluation_is_deterministic(score: int) -> None:
    node = {"kind": "comparison", "operator": ">=", "left": {"kind": "applicant", "path": "score"}, "right": 90}
    data = EvaluationData(applicant={"score": score})
    assert evaluate(node, data).value == (score >= 90)
