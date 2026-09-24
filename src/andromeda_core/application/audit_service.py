"""Small audit writer shared by application use cases."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from andromeda_core.domain.common import utc_now
from andromeda_core.domain.ports.observability import correlation_id_context
from andromeda_core.domain.ports.repositories import RepositoryPort


async def record_audit(
    repo: RepositoryPort,
    *,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str | None = None,
    source_id: str | None = None,
) -> dict[str, Any]:
    return await repo.create_audit(
        {
            "id": str(uuid4()),
            "actor": actor,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "before_json": before,
            "after_json": after,
            "reason": reason,
            "source_id": source_id,
            "correlation_id": correlation_id_context.get(),
            "created_at": utc_now(),
        }
    )
