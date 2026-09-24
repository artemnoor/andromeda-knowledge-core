# Security boundary

The local role seam recognizes READER, EDITOR, REVIEWER, ADMIN and SYSTEM.
Mutation routes explicitly depend on the minimum role; a reader cannot activate
a rule by calling the URL directly. The default no-header role is READER for
local semantic reads. Production must replace this dependency with the
Andromeda identity provider before exposing admin routes.

Pydantic models reject unknown request fields. DSL kinds/operators/effects,
overlay paths and temporal intervals are allowlisted. SQL access is
parameterized through SQLAlchemy. Request bodies have a configurable
Content-Length limit, CORS origins are configured, and security response
headers are enabled by default.

Optimistic row_version checks guard ontology, rule, review and derived updates.
Natural keys and checksums make source/fact/observation/relation operations
idempotent where defined. Activation updates supersession, dependencies,
invalidation and audit in one session transaction.

Secrets do not live in repository files. Compose credentials are development
only and must be injected from a deployment secret manager outside local use.

