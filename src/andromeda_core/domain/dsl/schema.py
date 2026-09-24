"""Serializable Rule DSL vocabulary exposed to external extractors."""

from __future__ import annotations

from typing import Any

from andromeda_core.domain.common import EffectType
from andromeda_core.domain.dsl.ast import (
    AGGREGATION_OPERATORS,
    ALLOWED_KINDS,
    COMPARISON_OPERATORS,
    LOGICAL_OPERATORS,
    MEMBERSHIP_OPERATORS,
    QUANTIFIER_OPERATORS,
)


def rule_dsl_schema() -> dict[str, Any]:
    """Return a JSON-safe snapshot of the closed rule vocabulary."""

    return {
        "schema_version": "1",
        "node_kinds": sorted(ALLOWED_KINDS),
        "operators": {
            "logical": sorted(LOGICAL_OPERATORS),
            "comparison": sorted(COMPARISON_OPERATORS),
            "membership": sorted(MEMBERSHIP_OPERATORS),
            "aggregation": sorted(AGGREGATION_OPERATORS),
            "quantifier": sorted(QUANTIFIER_OPERATORS),
        },
        "effect_types": sorted(effect.value for effect in EffectType),
    }
