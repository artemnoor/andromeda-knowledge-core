# Dependency graph

Dependencies are directed edges from a source node to a derived node. Source
kinds include fact, fact_property selector, relation, relation_type selector,
rule, rule catalog and ontology; derived-to-derived edges are also supported
for future multi-stage projections.

~~~mermaid
flowchart LR
  F[Fact] --> D1[AdmissionScore]
  R[Rule v1] --> D1
  D1 --> D2[Eligibility]
  D2 --> D3[Recommendation]
~~~

When a canonical source changes, DependencyService performs deterministic
reverse traversal using a queue and visited set. It returns affected_nodes,
invalidated_nodes, edge_count and duration_ms. Only VALID derived rows in the
affected set are marked INVALIDATED. Re-evaluation reconstructs a result key
from current canonical data, rule versions, ontology version, context and
engine version.

Dependency edges are unique and indexed in both directions. Self-edges and
detected reverse edges are rejected with DEPENDENCY_CYCLE. The service never
falls back to invalidating all universities or all results.

The derived cache is a materialized projection. Invalidating or rebuilding it
does not alter canonical facts, observations, sources or rules.

Selector dependencies are important for correctness: a query that currently
finds no fact or relation still depends on the property/predicate selector, so
later ingestion of the first matching row invalidates that projection. A new
active rule invalidates the rule catalog for its ontology; replacements use
the narrower old-rule edge whenever possible.
