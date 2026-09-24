# Provenance and explainability

Canonical facts, relations and rules carry provenance references. A provenance
record identifies a Source, optional Observation, extraction method and an
evidence locator such as page, section, paragraph, table or selector.

~~~mermaid
flowchart TB
  D[DerivedValue] --> R[Rule version]
  R --> F[Fact or Relation]
  F --> O[Observation]
  O --> S[Source / SourceDocument]
~~~

Source is a first-class record with source type, URL or external identity,
publisher, retrieval time, checksum, content metadata, trust metadata and
parser version. Observation is the assertion made by a source; it is not a
fact. Only an authorized acceptance flow promotes it to a canonical fact.

The explain endpoint returns a stable machine-readable tree and a concise
human-readable summary. Missing provenance is represented as a provenance
node with an explicit direct-provenance label; the API never invents an
observation or source. Demo facts intentionally use an observation so the
full source chain is visible in Swagger.

