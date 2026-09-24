# ADR 0001: PostgreSQL first

Status: accepted.

PostgreSQL is the physical source of truth. The graph is a logical domain model
of nodes, typed edges, facts, rules and dependencies. This keeps transactional
temporal/provenance data, constraints, audit and operational queries in one
store and avoids premature distributed consistency.

A graph database can be added behind ports if measured traversal workloads
justify it. Clients and the domain must not depend on that implementation.

