"""Consumer-facing semantic operations and immutable what-if overlays."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from andromeda_core.application.computation_service import ComputationService
from andromeda_core.domain.errors import ValidationError


class SemanticService:
    def __init__(self, computation: ComputationService) -> None:
        self.computation = computation

    async def evaluate(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self.computation.evaluate(
            applicant=data.get("applicant", {}),
            context=data.get("context", {}),
            derived_type=data.get("derived_type", "admission_evaluation"),
            persist=data.get("persist", True),
        )

    async def simulate(self, data: dict[str, Any]) -> dict[str, Any]:
        base = deepcopy(data["base_context"])
        before = await self.evaluate({**base, "persist": False})
        after = deepcopy(base)
        applicant = after.setdefault("applicant", {})
        for override in data.get("overrides", []):
            _set_safe_path(applicant, override["property"], override["value"])
        after_result = await self.evaluate({**after, "persist": False})
        return {
            "before": before,
            "after": after_result,
            "delta": _delta(before.get("value", {}), after_result.get("value", {})),
            "overrides": data.get("overrides", []),
            "persisted_changes": [],
        }


def _set_safe_path(root: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    if not parts or any(not part or part.startswith("_") for part in parts) or len(parts) > 4:
        raise ValidationError("INVALID_OVERLAY", "Overlay property path is not allowed.", {"property": path})
    current = root
    for part in parts[:-1]:
        child = current.get(part)
        if child is None:
            child = {}
            current[part] = child
        if not isinstance(child, dict):
            raise ValidationError("INVALID_OVERLAY", "Overlay path crosses a scalar value.", {"property": path})
        current = child
    current[parts[-1]] = value


def _delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    keys = set(before) | set(after)
    for key in keys:
        if before.get(key) != after.get(key):
            result[key] = {"before": before.get(key), "after": after.get(key)}
    return result
