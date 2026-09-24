"""Small reproducible benchmark for the pure engine and logical graph.

The declared synthetic corpus is 10 universities, 5,000 programs, 30,000
facts and 1,000 rules. The engine run uses a compact query snapshot, while
the graph benchmark loads the full dependency edge population.
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Callable

from andromeda_core.domain.dependencies import DependencyEdge, DependencyGraph
from andromeda_core.domain.engine import EngineInput, RuleEngine

DATASET = {"universities": 10, "programs": 5_000, "facts": 30_000, "rules": 1_000}


def timed(function: Callable[[], object], rounds: int = 20) -> tuple[float, float]:
    samples: list[float] = []
    for _ in range(rounds):
        start = time.perf_counter()
        function()
        samples.append((time.perf_counter() - start) * 1000)
    samples.sort()
    return statistics.median(samples), samples[min(len(samples) - 1, int(len(samples) * 0.95))]


def main() -> None:
    engine = RuleEngine()
    rules = tuple(
        {
            "id": f"rule-{index:04d}",
            "logical_key": f"synthetic.rule.{index:04d}",
            "version": 1,
            "status": "ACTIVE",
            "priority": index % 20,
            "scope_json": {},
            "conditions_json": {"kind": "exists", "target": {"kind": "context", "path": "benchmark_flag"}},
            "effects_json": [{"type": "ADD", "target": f"metric_{index % 8}", "value": 1}],
            "exceptions_json": [],
        }
        for index in range(DATASET["rules"])
    )
    query_facts = tuple({"id": f"fact-{index}", "property_code": "metric.synthetic", "value": index} for index in range(100))
    graph = DependencyGraph()
    for index in range(DATASET["facts"]):
        graph.add(DependencyEdge("fact", f"fact-{index}", "derived", f"derived-{index % DATASET['programs']}"))
    for index in range(DATASET["rules"]):
        graph.add(DependencyEdge("rule", f"rule-{index:04d}", "derived", f"derived-{index % DATASET['programs']}"))

    def evaluate() -> object:
        return engine.evaluate(EngineInput(facts=query_facts, context={"benchmark_flag": True}, applicant={}, relations=(), rules=rules, ontology_version_id="v1", engine_version="benchmark"))

    def lookup() -> object:
        return graph.affected(("fact", "fact-1234"))

    def invalidate() -> object:
        return graph.affected(("rule", "rule-0420"))

    print(f"dataset={DATASET}")
    for name, function in (("rule_evaluation_ms", evaluate), ("dependency_lookup_ms", lookup), ("incremental_invalidation_ms", invalidate)):
        median, p95 = timed(function)
        print(f"{name}: median={median:.3f} p95={p95:.3f}")


if __name__ == "__main__":
    main()
