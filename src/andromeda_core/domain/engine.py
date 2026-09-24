"""Universal deterministic Rule Engine.

The engine understands only the DSL, generic scopes and registered effect
kinds. It does not contain education-specific policy branches.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from hashlib import sha256
from typing import Any

from andromeda_core.domain.common import EffectType, RuleStatus
from andromeda_core.domain.dsl.ast import canonicalize
from andromeda_core.domain.dsl.evaluator import (
    EvaluationData,
    EvaluationTrace,
    evaluate,
    resolve_value,
)
from andromeda_core.domain.errors import ValidationError
from andromeda_core.domain.ports.observability import RuleExecutionObserver
from andromeda_core.domain.rules import scope_matches


@dataclass(frozen=True, slots=True)
class EngineInput:
    facts: tuple[dict[str, Any], ...]
    relations: tuple[dict[str, Any], ...]
    context: dict[str, Any]
    applicant: dict[str, Any]
    rules: tuple[dict[str, Any], ...]
    ontology_version_id: str
    engine_version: str
    ontology: dict[str, Any] | None = None


@dataclass(slots=True)
class EffectAccumulator:
    context: dict[str, Any]
    scalars: dict[str, Any] = field(default_factory=dict)
    grants: list[dict[str, Any]] = field(default_factory=list)
    denials: list[dict[str, Any]] = field(default_factory=list)
    eligible: bool | None = None
    emitted: list[dict[str, Any]] = field(default_factory=list)
    set_priorities: dict[str, int] = field(default_factory=dict)

    def initial_value(self, target: str) -> Any:
        if target in self.scalars:
            return self.scalars[target]
        if target in self.context:
            return self.context[target]
        return 0


@dataclass(slots=True)
class EngineResult:
    derived_type: str
    value: dict[str, Any]
    trace: dict[str, Any]
    dependencies: set[tuple[str, str]]
    rule_versions: list[dict[str, Any]]
    matched_rules: list[dict[str, Any]]
    explanation_summary: str
    duration_ms: float

    def canonical_hash(self) -> str:
        stable_trace = {key: value for key, value in self.trace.items() if key != "duration_ms"}
        payload = {
            "derived_type": self.derived_type,
            "value": self.value,
            "trace": stable_trace,
            "rule_versions": self.rule_versions,
        }
        encoded = json.dumps(canonicalize(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return sha256(encoded.encode("utf-8")).hexdigest()


EffectHandler = Callable[[EffectAccumulator, dict[str, Any], EvaluationData], dict[str, Any]]


class RuleEngine:
    """Deterministic evaluator with an extensible generic effect registry."""

    def __init__(self, observer: RuleExecutionObserver | None = None) -> None:
        self._handlers: dict[str, EffectHandler] = {}
        self._observer = observer
        self.register_defaults()

    def register_effect(self, effect_type: str, handler: EffectHandler) -> None:
        self._handlers[effect_type] = handler

    def register_defaults(self) -> None:
        self.register_effect(EffectType.SET.value, _handle_set)
        self.register_effect(EffectType.ADD.value, _handle_add)
        self.register_effect(EffectType.SUBTRACT.value, _handle_subtract)
        self.register_effect(EffectType.GRANT.value, _handle_grant)
        self.register_effect(EffectType.DENY.value, _handle_deny)
        self.register_effect(EffectType.MARK_ELIGIBLE.value, _handle_mark_eligible)
        self.register_effect(EffectType.MARK_INELIGIBLE.value, _handle_mark_ineligible)
        self.register_effect(EffectType.EMIT_DERIVED.value, _handle_emit_derived)

    def evaluate(self, engine_input: EngineInput) -> EngineResult:
        started = time.perf_counter()
        data = EvaluationData(
            facts=engine_input.facts,
            relations=engine_input.relations,
            context=engine_input.context,
            applicant=engine_input.applicant,
        )
        accumulator = EffectAccumulator(dict(engine_input.context))
        trace_rules: list[dict[str, Any]] = []
        dependencies: set[tuple[str, str]] = set()
        matched_rules: list[dict[str, Any]] = []
        rule_versions: list[dict[str, Any]] = []

        for rule in _ordered_rules(engine_input.rules):
            if rule.get("status") != RuleStatus.ACTIVE.value and rule.get("status") != RuleStatus.ACTIVE:
                continue
            rule_id = str(rule["id"])
            rule_trace: dict[str, Any] = {"rule_id": rule_id, "logical_key": rule.get("logical_key"), "version": rule.get("version")}
            if not scope_matches(rule.get("scope_json", rule.get("scope", {})), engine_input.context):
                rule_trace["status"] = "SCOPE_MISMATCH"
                trace_rules.append(rule_trace)
                continue
            # Only rules whose ontology-defined scope applies to this query
            # become dependencies of its derived result. A university-scoped
            # rule therefore cannot invalidate unrelated university results.
            rule_versions.append({"id": rule_id, "logical_key": rule.get("logical_key"), "version": rule.get("version")})
            condition = rule.get("conditions_json", rule.get("conditions"))
            condition_trace = evaluate(condition, data)
            dependencies.update(condition_trace.dependencies)
            rule_trace["condition"] = {"value": condition_trace.value, "steps": condition_trace.steps}
            if not bool(condition_trace.value):
                rule_trace["status"] = "NOT_MATCHED"
                trace_rules.append(rule_trace)
                continue
            exception_trace = _evaluate_exceptions(rule, data)
            dependencies.update(exception_trace.dependencies)
            rule_trace["exceptions"] = exception_trace.steps
            if exception_trace.value:
                rule_trace["status"] = "EXCEPTION"
                trace_rules.append(rule_trace)
                continue
            effect_traces: list[dict[str, Any]] = []
            for effect in rule.get("effects_json", rule.get("effects", [])):
                effect_type = effect.get("type")
                if effect_type == EffectType.SET.value and effect.get("target") in accumulator.set_priorities:
                    effect_traces.append(
                        {
                            "type": effect_type,
                            "target": effect.get("target"),
                            "status": "OVERRIDDEN_BY_HIGHER_PRIORITY",
                            "priority": rule.get("priority", 0),
                        }
                    )
                    continue
                handler = self._handlers.get(effect_type)
                if handler is None:
                    raise ValidationError("INVALID_EFFECT", f"Effect '{effect_type}' is not registered.")
                effect_result = handler(accumulator, effect, data)
                effect_traces.append(effect_result)
                if effect_type == EffectType.SET.value:
                    accumulator.set_priorities[effect["target"]] = int(rule.get("priority", 0))
            rule_trace["effects"] = effect_traces
            rule_trace["status"] = "MATCHED"
            matched_rules.append({"id": rule_id, "logical_key": rule.get("logical_key"), "version": rule.get("version")})
            trace_rules.append(rule_trace)

        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        if self._observer is not None:
            self._observer.record(duration_ms, "success")
        value = {
            "scalars": accumulator.scalars,
            "grants": accumulator.grants,
            "denials": accumulator.denials,
            "eligible": accumulator.eligible,
            "emitted": accumulator.emitted,
        }
        explanation = _build_explanation(matched_rules, accumulator)
        trace = {
            "engine_version": engine_input.engine_version,
            "ontology_version_id": engine_input.ontology_version_id,
            "ontology_definition_counts": {
                key: len(value)
                for key, value in (engine_input.ontology or {}).items()
                if isinstance(value, list)
            },
            "rules": trace_rules,
            "matched_rules": matched_rules,
            "duration_ms": duration_ms,
            "input": {"fact_count": len(engine_input.facts), "relation_count": len(engine_input.relations)},
        }
        return EngineResult(
            derived_type="semantic_evaluation",
            value=value,
            trace=trace,
            dependencies=dependencies,
            rule_versions=rule_versions,
            matched_rules=matched_rules,
            explanation_summary=explanation,
            duration_ms=duration_ms,
        )


def _ordered_rules(rules: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    return sorted(rules, key=lambda rule: (-int(rule.get("priority", 0)), str(rule.get("logical_key", "")), int(rule.get("version", 0))))


def _evaluate_exceptions(rule: dict[str, Any], data: EvaluationData) -> EvaluationTrace:
    exceptions = rule.get("exceptions_json", rule.get("exceptions", []))
    dependencies: set[tuple[str, str]] = set()
    steps: list[dict[str, Any]] = []
    for exception in exceptions:
        result = evaluate(exception, data)
        dependencies.update(result.dependencies)
        steps.extend(result.steps)
        if result.value:
            return EvaluationTrace(True, dependencies, steps)
    return EvaluationTrace(False, dependencies, steps)


def _value(effect: dict[str, Any], data: EvaluationData) -> Any:
    return resolve_value(effect.get("value"), data).value


def _handle_set(accumulator: EffectAccumulator, effect: dict[str, Any], data: EvaluationData) -> dict[str, Any]:
    value = _value(effect, data)
    accumulator.scalars[effect["target"]] = value
    return {"type": "SET", "target": effect["target"], "value": value}


def _handle_add(accumulator: EffectAccumulator, effect: dict[str, Any], data: EvaluationData) -> dict[str, Any]:
    value = _value(effect, data)
    current = accumulator.initial_value(effect["target"])
    accumulator.scalars[effect["target"]] = _number_result(_numeric(current) + _numeric(value))
    return {"type": "ADD", "target": effect["target"], "value": value, "result": accumulator.scalars[effect["target"]]}


def _handle_subtract(accumulator: EffectAccumulator, effect: dict[str, Any], data: EvaluationData) -> dict[str, Any]:
    value = _value(effect, data)
    current = accumulator.initial_value(effect["target"])
    accumulator.scalars[effect["target"]] = _number_result(_numeric(current) - _numeric(value))
    return {"type": "SUBTRACT", "target": effect["target"], "value": value, "result": accumulator.scalars[effect["target"]]}


def _handle_grant(accumulator: EffectAccumulator, effect: dict[str, Any], data: EvaluationData) -> dict[str, Any]:
    value = _value(effect, data)
    grant = {"target": effect["target"], "value": value}
    accumulator.grants.append(grant)
    return {"type": "GRANT", **grant}


def _handle_deny(accumulator: EffectAccumulator, effect: dict[str, Any], data: EvaluationData) -> dict[str, Any]:
    value = _value(effect, data)
    denial = {"target": effect["target"], "value": value}
    accumulator.denials.append(denial)
    return {"type": "DENY", **denial}


def _handle_mark_eligible(accumulator: EffectAccumulator, effect: dict[str, Any], _: EvaluationData) -> dict[str, Any]:
    accumulator.eligible = True
    return {"type": "MARK_ELIGIBLE", "target": effect["target"], "value": True}


def _handle_mark_ineligible(accumulator: EffectAccumulator, effect: dict[str, Any], _: EvaluationData) -> dict[str, Any]:
    accumulator.eligible = False
    return {"type": "MARK_INELIGIBLE", "target": effect["target"], "value": False}


def _handle_emit_derived(accumulator: EffectAccumulator, effect: dict[str, Any], data: EvaluationData) -> dict[str, Any]:
    emitted = {"type": effect["target"], "value": _value(effect, data)}
    accumulator.emitted.append(emitted)
    return {"type": "EMIT_DERIVED", **emitted}


def _numeric(value: Any) -> Decimal:
    if isinstance(value, bool) or value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise ValidationError("DSL_TYPE_MISMATCH", "ADD/SUBTRACT effects require numeric values.") from exc


def _number_result(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _build_explanation(matched_rules: list[dict[str, Any]], accumulator: EffectAccumulator) -> str:
    if not matched_rules:
        return "No active rule matched the supplied context."
    rule_text = ", ".join(f"{rule['logical_key']} v{rule['version']}" for rule in matched_rules)
    parts = [f"Matched rules: {rule_text}."]
    if accumulator.scalars:
        parts.append(f"Computed values: {accumulator.scalars}.")
    if accumulator.grants:
        parts.append(f"Granted benefits: {accumulator.grants}.")
    if accumulator.eligible is not None:
        parts.append(f"Eligibility: {'eligible' if accumulator.eligible else 'ineligible'}.")
    return " ".join(parts)
