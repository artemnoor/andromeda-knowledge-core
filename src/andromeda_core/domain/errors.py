"""Domain errors translated by the HTTP boundary into stable API errors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DomainError(Exception):
    """An expected business failure with a stable machine-readable code."""

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    status_code: int = 400

    def __str__(self) -> str:
        return self.message


class NotFoundError(DomainError):
    def __init__(self, entity: str, entity_id: str) -> None:
        super().__init__("NOT_FOUND", f"{entity} '{entity_id}' was not found.", {"entity": entity})
        self.status_code = 404


class ForbiddenError(DomainError):
    def __init__(self, message: str = "This operation is not permitted for the current role.") -> None:
        super().__init__("FORBIDDEN", message, status_code=403)


class PayloadTooLargeError(DomainError):
    def __init__(self, limit: int) -> None:
        super().__init__("REQUEST_TOO_LARGE", "Request body exceeds the configured limit.", {"limit_bytes": limit}, 413)


class ConflictError(DomainError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(code, message, details or {}, 409)


class ValidationError(DomainError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(code, message, details or {}, 422)


class ActivationError(DomainError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__("ACTIVATION_GUARD_FAILED", message, details or {}, 409)


class DependencyCycleError(ConflictError):
    def __init__(self, source: str, target: str) -> None:
        super().__init__(
            "DEPENDENCY_CYCLE",
            "The dependency graph would contain a cycle.",
            {"source": source, "target": target},
        )


class DependencyTraversalError(ConflictError):
    def __init__(self, max_nodes: int) -> None:
        super().__init__("DEPENDENCY_GRAPH_LIMIT", "Dependency traversal exceeded its safety bound.", {"max_nodes": max_nodes})


class RuleConflictError(ConflictError):
    def __init__(self, rule_ids: list[str], review_id: str | None = None) -> None:
        details: dict[str, Any] = {"rule_ids": rule_ids}
        if review_id:
            details["review_id"] = review_id
        super().__init__("RULE_CONFLICT", "The rule conflicts with an active rule and needs review.", details)
