"""Pure dependency graph primitives used by tests and future adapters."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from andromeda_core.domain.errors import DependencyCycleError


@dataclass(frozen=True, slots=True)
class DependencyEdge:
    source_kind: str
    source_id: str
    target_kind: str
    target_id: str
    dependency_type: str = "SUPPORTS"


class DependencyGraph:
    """Deterministic in-memory graph with bounded reverse traversal."""

    def __init__(self) -> None:
        self._outgoing: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)

    def add(self, edge: DependencyEdge) -> None:
        source = (edge.source_kind, edge.source_id)
        target = (edge.target_kind, edge.target_id)
        if source == target or self.has_path(target, source):
            raise DependencyCycleError(f"{edge.source_kind}:{edge.source_id}", f"{edge.target_kind}:{edge.target_id}")
        self._outgoing[source].add(target)

    def has_path(self, source: tuple[str, str], target: tuple[str, str]) -> bool:
        queue = deque([source])
        visited: set[tuple[str, str]] = set()
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            if current == target:
                return True
            visited.add(current)
            queue.extend(sorted(self._outgoing.get(current, set())))
        return False

    def affected(self, source: tuple[str, str], max_nodes: int = 10_000) -> list[tuple[str, str]]:
        queue = deque([source])
        visited: set[tuple[str, str]] = set()
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            if len(visited) > max_nodes:
                raise RuntimeError("Dependency traversal exceeded its safety bound.")
            queue.extend(sorted(self._outgoing.get(current, set())))
        return sorted(visited - {source})
