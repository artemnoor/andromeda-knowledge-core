"""Deterministic change classification independent of ingestion adapters."""

from __future__ import annotations

from typing import Any

from andromeda_core.domain.common import ChangeClassification


class ChangeDetectionService:
    @staticmethod
    def classify_fact(before: dict[str, Any] | None, after: dict[str, Any] | None) -> ChangeClassification:
        if before is None and after is not None:
            return ChangeClassification.NEW_FACT
        if before is not None and after is None:
            return ChangeClassification.FACT_REMOVED
        return ChangeClassification.FACT_CHANGED

    @staticmethod
    def classify_relation(before: dict[str, Any] | None, after: dict[str, Any] | None) -> ChangeClassification:
        if before is None and after is not None:
            return ChangeClassification.NEW_RELATION
        return ChangeClassification.RELATION_CHANGED

    @staticmethod
    def classify_rule(before: dict[str, Any] | None, after: dict[str, Any] | None) -> ChangeClassification:
        if before is None and after is not None:
            return ChangeClassification.NEW_RULE
        if before is not None and after is None:
            return ChangeClassification.RULE_REMOVED
        return ChangeClassification.RULE_CHANGED
