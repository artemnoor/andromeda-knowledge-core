# Operations and observability

Every request receives or validates an X-Correlation-ID. The same ID is
returned in the response header and is available to structured log records.
Request bodies are not logged.

JSON log events include timestamp, level, logger, event, correlation_id,
method, path, status_code and duration_ms when applicable. Application audit
events retain actor, action, entity, before/after snapshots, reason, source and
timestamp.

Prometheus-compatible /metrics exposes request count/duration, rule execution
count/duration, recomputation outcomes and stable API error counts. Useful
events include RULE_VALIDATED, RULE_TESTED, RULE_ACTIVATED, DERIVED_INVALIDATED,
DERIVED_RECOMPUTED, REVIEW_* and FACT_ACCEPTED.

The /health endpoint is liveness and does not require the database. The /ready
endpoint runs a database connectivity check and returns 503 when the configured
dependency is unavailable. Migrations run before the API in Compose.

