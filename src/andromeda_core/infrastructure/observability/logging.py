"""Structured logging setup and correlation context."""

from __future__ import annotations

import json
import logging
import sys

from andromeda_core.domain.ports.observability import correlation_id_context


def configure_logging(level: str) -> None:
    class JsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            payload = {
                "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
                "level": record.levelname,
                "logger": record.name,
                "event": getattr(record, "event", record.getMessage()),
                "correlation_id": correlation_id_context.get(),
            }
            for field in ("method", "path", "status_code", "duration_ms", "environment", "reason"):
                if hasattr(record, field):
                    payload[field] = getattr(record, field)
            return json.dumps(payload, ensure_ascii=False, default=str)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
        force=True,
    )
    for handler in logging.getLogger().handlers:
        handler.setFormatter(JsonFormatter())


def bind_correlation_id(value: str) -> None:
    correlation_id_context.set(value)


def log_event(level: int, event: str, **fields: object) -> None:
    logging.getLogger("andromeda").log(level, event, extra={"event": event, **fields})
