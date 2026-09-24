"""Rule data contracts, effect validation, scope matching and conflict policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from andromeda_core.domain.common import EffectType, RuleStatus
from andromeda_core.domain.dsl.ast import require_valid_dsl
from andromeda_core.domain.errors import ValidationError


@dataclass(frozen=True, slots=True)
class RuleRecord:
    id: str
    logical_key: str
    version: int
    rule_type: str
    scope: dict[str, Any]
    conditions: dict[str, Any]
    effects: list[dict[str, Any]]
    exceptions: list[dict[str, Any]]
    priority: int
    valid_from: datetime | None
    valid_to: datetime | None
    transaction_from: datetime
    transaction_to: datetime | None
    provenance_id: str | None
    status: RuleStatus
    ontology_version_id: str
    replaces_rule_id: str | None = None
    row_version: int = 1
    test_cases: tuple[dict[str, Any], ...] = ()
    validation_report: dict[str, Any] = field(default_factory=dict)


ALLOWED_EFFECTS = {effect.value for effect in EffectType}
RULE_RELATION_TYPES = {"REPLACES", "OVERRIDES", "EXCLUDES", "CONFLICTS_WITH"}


def validate_rule_payload(payload: dict[str, Any], *, max_dsl_depth: int = 30) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    condition_report = _safe_validate_condition(payload.get("conditions"), max_dsl_depth)
    errors.extend(condition_report.get("errors", []))
    for index, exception in enumerate(payload.get("exceptions", [])):
        report = _safe_validate_condition(exception, max_dsl_depth)
        errors.extend({**error, "path": f"exceptions[{index}].{error['path']}"} for error in report.get("errors", []))
    effects = payload.get("effects")
    if not isinstance(effects, list) or not effects:
        errors.append({"path": "effects", "message": "At least one declarative effect is required."})
    else:
        for index, effect in enumerate(effects):
            errors.extend(_validate_effect(effect, index))
    if not isinstance(payload.get("logical_key"), str) or not payload["logical_key"].strip():
        errors.append({"path": "logical_key", "message": "logical_key is required."})
    if not isinstance(payload.get("ontology_version_id"), str):
        errors.append({"path": "ontology_version_id", "message": "ontology_version_id is required."})
    return {"valid": not errors, "errors": errors}


def _safe_validate_condition(node: Any, max_depth: int) -> dict[str, Any]:
    try:
        require_valid_dsl(node, max_depth=max_depth)
        return {"valid": True, "errors": []}
    except ValidationError as exc:
        return {"valid": False, "errors": [*exc.details.get("errors", [{"path": "$", "message": exc.message}])]}


def _validate_effect(effect: Any, index: int) -> list[dict[str, str]]:
    path = f"effects[{index}]"
    if not isinstance(effect, dict):
        return [{"path": path, "message": "Effect must be an object."}]
    errors: list[dict[str, str]] = []
    effect_type = effect.get("type")
    if effect_type not in ALLOWED_EFFECTS:
        errors.append({"path": f"{path}.type", "message": f"Unknown effect '{effect_type}'."})
    if not isinstance(effect.get("target"), str) or not effect["target"]:
        errors.append({"path": f"{path}.target", "message": "Effect target is required."})
    if effect_type not in {EffectType.MARK_ELIGIBLE.value, EffectType.MARK_INELIGIBLE.value} and "value" not in effect:
        errors.append({"path": f"{path}.value", "message": "This effect requires a value."})
    if isinstance(effect.get("value"), dict) and "kind" in effect["value"]:
        report = _safe_validate_condition(effect["value"], 30)
        errors.extend({**error, "path": f"{path}.{error['path']}"} for error in report.get("errors", []))
    return errors


def scope_matches(scope: dict[str, Any], context: dict[str, Any]) -> bool:
    """Match ontology-defined scope keys without naming institutions in code."""

    for key, expected in scope.items():
        actual = context.get(key)
        if isinstance(expected, list):
            if actual not in expected:
                return False
        elif isinstance(expected, dict) and isinstance(actual, dict):
            if not scope_matches(expected, actual):
                return False
        elif actual != expected:
            return False
    return True


def effect_conflicts(left: RuleRecord, right: RuleRecord) -> bool:
    if left.priority != right.priority or not _scopes_overlap(left.scope, right.scope):
        return False
    left_effects = _effect_map(left.effects)
    right_effects = _effect_map(right.effects)
    for target in left_effects.keys() & right_effects.keys():
        if left_effects[target] != right_effects[target]:
            return True
    return False


def _effect_map(effects: list[dict[str, Any]]) -> dict[str, tuple[str, Any]]:
    return {effect["target"]: (effect["type"], effect.get("value")) for effect in effects}


def _scopes_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    for key in left.keys() & right.keys():
        left_value, right_value = left[key], right[key]
        if isinstance(left_value, list) and isinstance(right_value, list):
            if not set(left_value) & set(right_value):
                return False
        elif left_value != right_value:
            return False
    return True
