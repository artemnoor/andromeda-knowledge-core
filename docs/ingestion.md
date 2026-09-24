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

## Durable refresh and retry

`IngestionPipelineService` treats `source + item + profile` as a stable stream
identity, not as a permanent cache key. Every run whose latest attempt is
`PUBLISHED` or `SKIPPED_UNCHANGED` fetches the source again and compares the
content checksum. A changed document creates a new attempt; an unchanged one
returns `SKIPPED_UNCHANGED` without re-running extraction.

Every successful stage persists its payload in `ingestion_pipeline_runs`.
When extraction exists but Core publication failed, the next run publishes
that saved extraction directly; it does not fetch or call the AI adapter again.
When only fetch succeeded, extraction resumes from the stored document bytes.
This prevents a Core outage from turning a valid extraction into a permanent
false `SKIPPED_UNCHANGED` result.

The `StructuredJsonHttpAIAdapter` receives the complete ontology snapshot
(object types, properties and relations) in both the system instruction and a
first-class request field. Provider output remains a proposal until the Core
publisher validates and accepts it.

The HTTP source adapter validates DNS results, rejects private/non-global
addresses and credentials, bounds redirects and response size, and converts
4xx/5xx responses to safe source errors. Discovery supports static URLs,
sitemaps and same-origin HTML links. Evidence locators include document hashes
and deterministic HTML/PDF offsets where available.

Observation states are RAW, PARSED, MAPPED, VALIDATED, ACCEPTED, REJECTED and
NEEDS_REVIEW. Unknown ontology concepts, low confidence, conflicting source
claims and suspicious changes are reviewable outcomes. Accepted observations
create a ProvenanceRecord and typed Fact or Relation inside one application
transaction.

ChangeDetectionService classifies NEW_FACT, FACT_CHANGED, FACT_REMOVED,
NEW_RELATION, RELATION_CHANGED, NEW_RULE, RULE_CHANGED, RULE_REMOVED,
UNKNOWN_CONCEPT and CONFLICT. The changes and audit endpoints expose these
records to review tooling.
