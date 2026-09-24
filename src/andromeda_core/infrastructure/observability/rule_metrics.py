"""Prometheus adapter for the domain rule execution observer port."""

from __future__ import annotations

from andromeda_core.infrastructure.observability.metrics import (
    rule_execution_duration_seconds,
    rule_executions_total,
)


class PrometheusRuleExecutionObserver:
    def record(self, duration_ms: float, outcome: str) -> None:
        rule_executions_total.labels(outcome).inc()
        rule_execution_duration_seconds.observe(duration_ms / 1000)
