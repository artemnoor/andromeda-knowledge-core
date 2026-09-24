from __future__ import annotations

import pytest

from andromeda_core.domain.dependencies import DependencyEdge, DependencyGraph
from andromeda_core.domain.errors import DependencyCycleError


def test_dependency_graph_is_deterministic_and_rejects_cycles() -> None:
    graph = DependencyGraph()
    graph.add(DependencyEdge("fact", "f-2", "derived", "d-2"))
    graph.add(DependencyEdge("derived", "d-2", "derived", "d-3"))
    assert graph.affected(("fact", "f-2")) == [("derived", "d-2"), ("derived", "d-3")]
    with pytest.raises(DependencyCycleError):
        graph.add(DependencyEdge("derived", "d-3", "fact", "f-2"))
