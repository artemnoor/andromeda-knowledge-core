# AI and Jev boundaries

The core defines ports for document understanding, entity resolution, ontology
mapping, rule extraction and change interpretation. Mock adapters implement the
ports for tests and local development. A future Jev or LLM adapter can be
composed without importing its SDK into domain code.

AI output is a Proposal with payload, confidence, evidence references and
adapter identity. It is not a Fact, active Rule or active OntologyVersion.

~~~mermaid
flowchart LR
  AI[AI/Jev adapter] --> P[Proposal + evidence]
  P --> R[Review / validation]
  R --> O[Observation or draft rule]
  O --> H[Human/policy activation]
  H --> K[Canonical knowledge]
~~~

No adapter is allowed to call activation operations. External content is
treated as untrusted data; the mock rule adapter hashes bytes and returns a
draft proposal without executing text. The core does not require external
credentials and CI uses mocks.

