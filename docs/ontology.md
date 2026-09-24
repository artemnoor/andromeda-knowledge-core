# Ontology and semantic evolution

Ontology versions define the allowed meaning of objects, properties and
relations. An active version is immutable. A semantic change creates a new
version with previous_version, change_type and migration requirements.

~~~mermaid
stateDiagram-v2
  [*] --> DRAFT
  DRAFT --> VALIDATING
  VALIDATING --> ACTIVE: compatible
  VALIDATING --> MIGRATING: breaking
  MIGRATING --> ACTIVE: migration complete
  ACTIVE --> SUPERSEDED: next version activated
  DRAFT --> REJECTED
~~~

The core definitions are:

- ObjectType: the type of a KnowledgeObject;
- PropertyDefinition: typed scalar/reference/collection semantics and allowed
  object types;
- RelationType: predicate, source/target type allowlists and cardinality;
- OntologyChangeProposal: proposed types/properties/relations, evidence,
  confidence and impact analysis.

The version does not silently inherit edits. Seed and migration workflows copy
or add definitions explicitly, which makes semantic changes reviewable.

## Unknown concepts

Ingestion first maps an Observation against the active ontology. An absent
property, object type or relation produces UNKNOWN_CONCEPT, an
OntologyChangeProposal and a ReviewItem. The active version is unchanged.
Approval records a human decision and a later migration is responsible for
adding the definition to a new version.

Breaking changes cannot be activated directly. They need migration status,
impact analysis and reviewer authorization.

## Objects and relations

A KnowledgeObject has a stable_key, object type, display name, extensible
non-semantic attributes and lifecycle/temporal metadata. Facts are typed
claims about an object. Relations are first-class edges with subject,
predicate, object, temporal metadata, provenance, confidence and status.

Rules have a dedicated rule_relations table for REPLACES, OVERRIDES, EXCLUDES
and CONFLICTS_WITH. The engine uses priority as a deterministic policy for
compatible rules; equal-priority contradictory effects are not auto-resolved.

