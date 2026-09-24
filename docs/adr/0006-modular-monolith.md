# ADR 0006: Modular monolith

Status: accepted.

The core has strong bounded contexts but one deployable transaction boundary.
This keeps activation plus invalidation atomic and avoids network coordination
before workload evidence exists. Ports and application boundaries leave a path
to extract heavy adapters or workers later.

