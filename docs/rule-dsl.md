# Rule DSL

The DSL is a closed, JSON-serializable AST. It is validated before persistence
and evaluated by a pure interpreter. Python eval, dynamic imports, callbacks
and arbitrary code are not part of the execution path.

## Node shapes

~~~json
{
  "kind": "logical",
  "operator": "and",
  "args": [
    {"kind": "exists", "target": {"kind": "applicant", "path": "additional_exams"}},
    {"kind": "comparison", "operator": ">=",
     "left": {"kind": "applicant", "path": "scores.physics"}, "right": 90}
  ]
}
~~~

Supported references are fact/facts/collection, relation/relations, context
and applicant. Operators are logical and/or/not, comparison == != > >= < <=,
membership in/not_in, exists/not_exists, aggregation count/sum/min/max and
quantifiers any/all/none/at_least.

A reference missing from the snapshot is unknown/null. It is not silently
converted to zero. Numeric comparisons exclude booleans and report a typed
DSL_TYPE_MISMATCH for incompatible values.

## Effects

Effects are data records with a type, target and optional value. The default
registry provides SET, ADD, SUBTRACT, GRANT, DENY, MARK_ELIGIBLE,
MARK_INELIGIBLE and EMIT_DERIVED. An application can register another generic
handler at composition time; it must be deterministic and must not execute
arbitrary source text.

SET effects obey the documented priority policy: a higher-priority SET claims
a target and a lower-priority SET is traced as overridden. Equal-priority
contradictory effects are blocked by RuleService conflict detection.

## Lifecycle

~~~mermaid
stateDiagram-v2
  [*] --> DRAFT
  DRAFT --> VALIDATING: validate
  VALIDATING --> TESTING: valid AST
  TESTING --> REVIEW: all cases pass
  REVIEW --> ACTIVE: reviewer activates
  ACTIVE --> SUPERSEDED: replacement
  ACTIVE --> REVOKED: revoke
~~~

Activation requires a valid AST, at least one passing persisted test, rule
provenance and no unresolved equal-priority conflict. Each evaluation records
the exact rule IDs and versions, engine version, ontology version and an
explanation trace.

