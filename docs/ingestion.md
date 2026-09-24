# Ingestion pipeline

The pipeline is intentionally staged:

~~~mermaid
flowchart LR
  S[Source] --> O[Observation]
  O --> N[Normalization]
  N --> M[Ontology mapping]
  M --> V[Validation]
  V --> F[Fact or Rule proposal]
  F --> A[Human/activation policy]
  A --> I[Dependency invalidation]
  I --> C[Incremental recalculation]
~~~

SourceAdapter implementations fetch and parse into ObservationCandidate
records. The adapter cannot receive a repository, so it cannot write a Fact.
The application assigns an idempotency key from an explicit Idempotency-Key
header or a canonical natural identity composed from source, candidate, value,
evidence and raw payload fields.

Observation states are RAW, PARSED, MAPPED, VALIDATED, ACCEPTED, REJECTED and
NEEDS_REVIEW. Unknown ontology concepts, low confidence, conflicting source
claims and suspicious changes are reviewable outcomes. Accepted observations
create a ProvenanceRecord and typed Fact or Relation inside one application
transaction.

ChangeDetectionService classifies NEW_FACT, FACT_CHANGED, FACT_REMOVED,
NEW_RELATION, RELATION_CHANGED, NEW_RULE, RULE_CHANGED, RULE_REMOVED,
UNKNOWN_CONCEPT and CONFLICT. The changes and audit endpoints expose these
records to review tooling.
