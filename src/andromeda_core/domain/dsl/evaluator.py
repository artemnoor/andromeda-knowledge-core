"""Pure evaluator for the Rule DSL."""

from __future__ import annotations

import operator as operator_module
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from andromeda_core.domain.dsl.ast import validate_dsl
from andromeda_core.domain.errors import ValidationError


@dataclass(frozen=True, slots=True)
class EvaluationData:
    facts: tuple[dict[str, Any], ...] = ()
    relations: tuple[dict[str, Any], ...] = ()
    context: dict[str, Any] = field(default_factory=dict)
    applicant: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EvaluationTrace:
    value: Any
    dependencies: set[tuple[str, str]] = field(default_factory=set)
    steps: list[dict[str, Any]] = field(default_factory=list)


def evaluate(node: Any, data: EvaluationData) -> EvaluationTrace:
    report = validate_dsl(node)
    if not report["valid"]:
        raise ValidationError("INVALID_DSL", "Cannot evaluate an invalid DSL node.", report)
    return _evaluate(node, data)


def resolve_value(node: Any, data: EvaluationData) -> EvaluationTrace:
    if isinstance(node, dict) and "kind" in node:
        return _evaluate(node, data)
    return EvaluationTrace(node)


def _evaluate(node: Any, data: EvaluationData) -> EvaluationTrace:
    if not isinstance(node, dict):
        return EvaluationTrace(node)
    kind = node.get("kind", node.get("op"))
    if kind == "literal":
        return EvaluationTrace(node.get("value"))
    if kind in {"fact", "facts", "collection"}:
        return _fact_reference(node, data)
    if kind in {"relation", "relations"}:
        return _relation_reference(node, data)
    if kind in {"context", "applicant"}:
        root = data.context if kind == "context" else data.applicant
        value = _get_path(root, node["path"])
        return EvaluationTrace(value, {("context" if kind == "context" else "applicant", node["path"])})
    if kind == "logical":
        return _logical(node, data)
    if kind == "comparison":
        return _comparison(node, data)
    if kind in {"exists", "not_exists"}:
        target = _evaluate(node["target"], data)
        exists = target.value is not None and target.value != []
        return EvaluationTrace(exists if kind == "exists" else not exists, target.dependencies, target.steps)
    if kind == "membership":
        left = _evaluate(node["left"], data)
        right = _evaluate(node["right"], data)
        values = right.value if isinstance(right.value, (list, tuple, set)) else [right.value]
        result = left.value in values
        if node["operator"] == "not_in":
            result = not result
        return _merge(result, left, right, "membership", node["operator"])
    if kind == "aggregation":
        target = _evaluate(node["target"], data)
        values = target.value if isinstance(target.value, list) else ([] if target.value is None else [target.value])
        result = _aggregate(node["operator"], values)
        return EvaluationTrace(result, target.dependencies, target.steps + [{"operation": node["operator"], "value": result}])
    if kind == "quantifier":
        traces = [_evaluate(item, data) for item in node["items"]]
        values = [bool(trace.value) for trace in traces]
        result = _quantify(node["operator"], values, node.get("count"))
        dependencies = set().union(*(trace.dependencies for trace in traces))
        steps = [step for trace in traces for step in trace.steps]
        steps.append({"operation": node["operator"], "values": values, "value": result})
        return EvaluationTrace(result, dependencies, steps)
    raise ValidationError("INVALID_DSL", f"Unsupported DSL node '{kind}'.")


def _fact_reference(node: dict[str, Any], data: EvaluationData) -> EvaluationTrace:
    property_code = node["property"]
    matches = [fact for fact in data.facts if _matches_pattern(fact.get("property_code"), property_code)]
    if node.get("subject_id"):
        matches = [fact for fact in matches if fact.get("subject_id") == node["subject_id"]]
    values = [fact.get("value") for fact in matches]
    dependencies = {("fact", str(fact["id"])) for fact in matches if fact.get("id")}
    # Preserve a dependency even when the current query has no matching row.
    dependencies.add(("fact_property", property_code))
    if node.get("kind") == "fact":
        value: Any = values[0] if values else None
    else:
        value = values
    return EvaluationTrace(value, dependencies, [{"reference": "fact", "property": property_code, "count": len(matches)}])


def _relation_reference(node: dict[str, Any], data: EvaluationData) -> EvaluationTrace:
    relation_type = node["relation_type"]
    matches = [
        relation
        for relation in data.relations
        if relation.get("relation_type_code") == relation_type
        and (not node.get("subject_id") or relation.get("subject_id") == node["subject_id"])
        and (not node.get("object_id") or relation.get("object_id") == node["object_id"])
    ]
    dependencies = {("relation", str(relation["id"])) for relation in matches if relation.get("id")}
    dependencies.add(("relation_type", relation_type))
    value = matches[0] if node.get("kind") == "relation" and matches else matches
    return EvaluationTrace(value, dependencies, [{"reference": "relation", "type": relation_type, "count": len(matches)}])


def _logical(node: dict[str, Any], data: EvaluationData) -> EvaluationTrace:
    traces = [_evaluate(child, data) for child in node["args"]]
    values = [bool(trace.value) for trace in traces]
    operation = node["operator"]
    result = all(values) if operation == "and" else any(values) if operation == "or" else not values[0]
    dependencies = set().union(*(trace.dependencies for trace in traces))
    steps = [step for trace in traces for step in trace.steps]
    steps.append({"operation": operation, "values": values, "value": result})
    return EvaluationTrace(result, dependencies, steps)


def _comparison(node: dict[str, Any], data: EvaluationData) -> EvaluationTrace:
    left = _evaluate(node["left"], data)
    right = _evaluate(node["right"], data)
    operation = node["operator"]
    try:
        result = _compare(left.value, right.value, operation)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "DSL_TYPE_MISMATCH",
            "The DSL comparison received incompatible values.",
            {"operator": operation, "left_type": type(left.value).__name__, "right_type": type(right.value).__name__},
        ) from exc
    return _merge(result, left, right, "comparison", operation)


def _compare(left: Any, right: Any, operation: str) -> bool:
    if left is None or right is None:
        return operation == "==" and left is right or operation == "!=" and left is not right
    functions = {
        "==": operator_module.eq,
        "!=": operator_module.ne,
        ">": operator_module.gt,
        ">=": operator_module.ge,
        "<": operator_module.lt,
        "<=": operator_module.le,
    }
    if isinstance(left, (int, float, Decimal)) and not isinstance(left, bool) and isinstance(right, (int, float, Decimal)) and not isinstance(right, bool):
        return bool(functions[operation](Decimal(str(left)), Decimal(str(right))))
    return bool(functions[operation](left, right))


def _aggregate(operation: str, values: list[Any]) -> Any:
    if operation == "count":
        return len(values)
    if not values:
        return None
    try:
        if operation == "sum":
            return sum(values)
        if operation == "min":
            return min(values)
        if operation == "max":
            return max(values)
    except (TypeError, ValueError) as exc:
        raise ValidationError("DSL_TYPE_MISMATCH", "Aggregation received incompatible values.") from exc
    raise ValidationError("INVALID_DSL", f"Unsupported aggregation '{operation}'.")


def _quantify(operation: str, values: list[bool], count: int | None) -> bool:
    true_count = sum(values)
    if operation == "any":
        return any(values)
    if operation == "all":
        return all(values)
    if operation == "none":
        return not any(values)
    if operation == "at_least":
        return true_count >= (count or 0)
    raise ValidationError("INVALID_DSL", f"Unsupported quantifier '{operation}'.")


def _merge(value: Any, left: EvaluationTrace, right: EvaluationTrace, operation: str, operator: str) -> EvaluationTrace:
    return EvaluationTrace(
        value,
        left.dependencies | right.dependencies,
        left.steps + right.steps + [{"operation": operation, "operator": operator, "value": value}],
    )


def _get_path(source: dict[str, Any], path: str) -> Any:
    value: Any = source
    for segment in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(segment)
    return value


def _matches_pattern(value: Any, pattern: str) -> bool:
    if not isinstance(value, str):
        return False
    return value == pattern or (pattern.endswith(".*") and value.startswith(pattern[:-1]))
