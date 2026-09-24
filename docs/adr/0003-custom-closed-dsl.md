# ADR 0003: Closed typed DSL

Status: accepted.

A small JSON AST is deterministic, serializable, versionable, testable and
explainable. Python eval and general-purpose expression languages would create
an unacceptable code-execution and audit boundary. New operators are explicit
engine changes; existing rules never execute arbitrary text.

