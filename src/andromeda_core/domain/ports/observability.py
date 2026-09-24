"""Observability ports kept independent from metric backends."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Protocol

correlation_id_context: ContextVar[str] = ContextVar("correlation_id", default="-")


class RuleExecutionObserver(Protocol):
    def record(self, duration_ms: float, outcome: str) -> None: ...
