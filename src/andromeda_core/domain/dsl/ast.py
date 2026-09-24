"""Validation and canonicalization for the closed Rule DSL.

The DSL intentionally consists of JSON objects with a finite set of node kinds.
It is not Python and is never compiled or evaluated as code.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from hashlib import sha256
from typing import Any

from andromeda_core.domain.errors import ValidationError

LOGICAL_OPERATORS = {"and", "or", "not"}
COMPARISON_OPERATORS = {"==", "!=", ">", ">=", "<", "<="}
MEMBERSHIP_OPERATORS = {"in", "not_in"}
AGGREGATION_OPERATORS = {"count", "sum", "min", "max"}
QUANTIFIER_OPERATORS = {"any", "all", "none", "at_least"}
REFERENCE_KINDS = {"fact", "facts", "relation", "relations", "context", "applicant", "collection"}
ALLOWED_KINDS = {
    "literal",
    "logical",
    "comparison",
    "exists",
    "not_exists",
    "membership",
    "aggregation",
    "quantifier",
    *REFERENCE_KINDS,
}


def canonicalize(value: Any) -> Any:
    """Return a recursively key-sorted JSON-compatible value."""

    if isinstance(value, Mapping):
        return {str(key): canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [canonicalize(item) for item in value]
    if isinstance(value, tuple):
        return [canonicalize(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(canonicalize(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def canonical_hash(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def validate_dsl(node: Any, *, max_depth: int = 30) -> dict[str, Any]:
    """Validate a DSL AST and return a serializable report."""

    errors: list[dict[str, str]] = []
    _validate_node(node, "$", 0, max_depth, errors)
    return {"valid": not errors, "errors": errors}


def require_valid_dsl(node: Any, *, max_depth: int = 30) -> None:
    report = validate_dsl(node, max_depth=max_depth)
    if not report["valid"]:
        raise ValidationError("INVALID_DSL", "The rule condition is not a valid DSL AST.", report)


def _validate_node(
    node: Any,
    path: str,
    depth: int,
    max_depth: int,
    errors: list[dict[str, str]],
) -> None:
    if depth > max_depth:
        errors.append({"path": path, "message": f"DSL nesting exceeds {max_depth} levels."})
        return
    if isinstance(node, (str, int, float, bool)) or node is None:
        return
    if isinstance(node, list):
        for index, child in enumerate(node):
            _validate_node(child, f"{path}[{index}]", depth + 1, max_depth, errors)
        return
    if not isinstance(node, Mapping):
        errors.append({"path": path, "message": "DSL node must be JSON object, array or literal."})
        return

    kind = node.get("kind", node.get("op"))
    if not isinstance(kind, str):
        errors.append({"path": path, "message": "DSL node requires a string 'kind'."})
        return
    if kind not in ALLOWED_KINDS:
        errors.append({"path": f"{path}.kind", "message": f"Unknown DSL node kind '{kind}'."})
        return

    if kind == "literal":
        if "value" not in node:
            errors.append({"path": path, "message": "Literal requires 'value'."})
        return
    if kind == "logical":
        operator = node.get("operator")
        args = node.get("args")
        if operator not in LOGICAL_OPERATORS:
            errors.append({"path": f"{path}.operator", "message": "Unknown logical operator."})
        if not isinstance(args, list) or (operator == "not" and len(args) != 1) or (
            operator in {"and", "or"} and len(args or []) < 1
        ):
            errors.append({"path": f"{path}.args", "message": "Logical arity is invalid."})
        for index, child in enumerate(args or []):
            _validate_node(child, f"{path}.args[{index}]", depth + 1, max_depth, errors)
        return
    if kind == "comparison":
        if node.get("operator") not in COMPARISON_OPERATORS:
            errors.append({"path": f"{path}.operator", "message": "Unknown comparison operator."})
        _validate_required_child(node, "left", path, depth, max_depth, errors)
        _validate_required_child(node, "right", path, depth, max_depth, errors)
        return
    if kind in {"exists", "not_exists"}:
        _validate_required_child(node, "target", path, depth, max_depth, errors)
        return
    if kind == "membership":
        if node.get("operator") not in MEMBERSHIP_OPERATORS:
            errors.append({"path": f"{path}.operator", "message": "Unknown membership operator."})
        _validate_required_child(node, "left", path, depth, max_depth, errors)
        _validate_required_child(node, "right", path, depth, max_depth, errors)
        return
    if kind == "aggregation":
        if node.get("operator") not in AGGREGATION_OPERATORS:
            errors.append({"path": f"{path}.operator", "message": "Unknown aggregation operator."})
        _validate_required_child(node, "target", path, depth, max_depth, errors)
        return
    if kind == "quantifier":
        operator = node.get("operator")
        if operator not in QUANTIFIER_OPERATORS:
            errors.append({"path": f"{path}.operator", "message": "Unknown quantifier operator."})
        items = node.get("items")
        if not isinstance(items, list) or not items:
            errors.append({"path": f"{path}.items", "message": "Quantifier requires non-empty items."})
        if operator == "at_least" and (not isinstance(node.get("count"), int) or node["count"] < 0):
            errors.append({"path": f"{path}.count", "message": "at_least requires a non-negative integer count."})
        for index, child in enumerate(items or []):
            _validate_node(child, f"{path}.items[{index}]", depth + 1, max_depth, errors)
        return
    _validate_reference(node, kind, path, errors)


def _validate_required_child(
    node: Mapping[str, Any],
    name: str,
    path: str,
    depth: int,
    max_depth: int,
    errors: list[dict[str, str]],
) -> None:
    if name not in node:
        errors.append({"path": f"{path}.{name}", "message": f"Missing '{name}'."})
    else:
        _validate_node(node[name], f"{path}.{name}", depth + 1, max_depth, errors)


def _validate_reference(node: Mapping[str, Any], kind: str, path: str, errors: list[dict[str, str]]) -> None:
    if kind in {"fact", "facts", "collection"} and not isinstance(node.get("property"), str):
        errors.append({"path": f"{path}.property", "message": "Fact reference requires a property."})
    if kind in {"relation", "relations"} and not isinstance(node.get("relation_type"), str):
        errors.append({"path": f"{path}.relation_type", "message": "Relation reference requires relation_type."})
    if kind in {"context", "applicant"} and not isinstance(node.get("path"), str):
        errors.append({"path": f"{path}.path", "message": "Context reference requires path."})
