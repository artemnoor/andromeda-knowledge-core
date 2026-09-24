"""Dependency graph traversal and targeted invalidation."""

from __future__ import annotations

import time
from collections import deque
from typing import Any
from uuid import uuid4

from andromeda_core.application.audit_service import record_audit
from andromeda_core.domain.common import utc_now
from andromeda_core.domain.errors import DependencyCycleError, DependencyTraversalError
from andromeda_core.domain.ports.repositories import RepositoryPort
from andromeda_core.infrastructure.observability.metrics import recomputations_total


class DependencyService:
    def __init__(self, repo: RepositoryPort) -> None:
        self.repo = repo

    async def invalidate(self, source_kind: str, source_id: str, reason: str) -> dict[str, Any]:
        started = time.perf_counter()
        queue = deque([(source_kind, source_id)])
        visited: set[tuple[str, str]] = set()
        affected: set[str] = set()
        edges: list[dict[str, Any]] = []
        max_nodes = 10_000
        while queue:
            kind, entity_id = queue.popleft()
            node = (kind, entity_id)
            if node in visited:
                continue
            visited.add(node)
            if len(visited) > max_nodes:
                raise DependencyTraversalError(max_nodes)
            for edge in await self.repo.dependencies_from(kind, entity_id):
                edges.append(edge)
                target = (edge["target_kind"], edge["target_id"])
                if target in visited:
                    continue
                if target[0] == "derived":
                    affected.add(target[1])
                queue.append(target)
        invalidated = await self.repo.invalidate_derived(sorted(affected), reason)
        if invalidated:
            await record_audit(
                repo=self.repo,
                actor="SYSTEM",
                action="DERIVED_INVALIDATED",
                entity_type="dependency_graph",
                entity_id=f"{source_kind}:{source_id}",
                after={"affected_nodes": sorted(affected), "invalidated_count": invalidated, "reason": reason},
            )
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        recomputations_total.labels("invalidated" if invalidated else "no_op").inc()
        return {
            "source": {"kind": source_kind, "id": source_id},
            "affected_nodes": sorted(affected),
            "invalidated_nodes": sorted(affected),
            "invalidated_count": invalidated,
            "edge_count": len(edges),
            "duration_ms": duration_ms,
        }

    async def register_edge(self, source_kind: str, source_id: str, target_kind: str, target_id: str, dependency_type: str = "SUPPORTS") -> dict[str, Any]:
        if source_kind == target_kind and source_id == target_id:
            raise DependencyCycleError(f"{source_kind}:{source_id}", f"{target_kind}:{target_id}")
        if await self._has_path((target_kind, target_id), (source_kind, source_id)):
            raise DependencyCycleError(f"{source_kind}:{source_id}", f"{target_kind}:{target_id}")
        return await self.repo.add_dependency({"id": str(uuid4()), "source_kind": source_kind, "source_id": source_id, "target_kind": target_kind, "target_id": target_id, "dependency_type": dependency_type, "created_at": utc_now(), "invalidated_at": None})

    async def _has_path(self, start: tuple[str, str], target: tuple[str, str]) -> bool:
        queue = deque([start])
        visited: set[tuple[str, str]] = set()
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            if current == target:
                return True
            visited.add(current)
            if len(visited) > 10_000:
                raise DependencyTraversalError(10_000)
            edges = await self.repo.dependencies_from(*current)
            queue.extend(sorted((edge["target_kind"], edge["target_id"]) for edge in edges))
        return False
