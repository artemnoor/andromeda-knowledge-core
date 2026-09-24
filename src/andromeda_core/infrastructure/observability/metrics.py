"""Prometheus-compatible metrics with stable names."""

from prometheus_client import Counter, Histogram, generate_latest

http_requests_total = Counter(
    "andromeda_http_requests_total",
    "HTTP requests handled by the core",
    ["method", "path", "status"],
)
http_request_duration_seconds = Histogram(
    "andromeda_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
)
rule_executions_total = Counter(
    "andromeda_rule_executions_total",
    "Rule evaluations by outcome",
    ["outcome"],
)
rule_execution_duration_seconds = Histogram(
    "andromeda_rule_execution_duration_seconds",
    "Rule engine duration in seconds",
)
recomputations_total = Counter(
    "andromeda_recomputations_total",
    "Derived recomputations by outcome",
    ["outcome"],
)
api_errors_total = Counter(
    "andromeda_api_errors_total",
    "API errors by stable domain code",
    ["code"],
)


def metrics_payload() -> bytes:
    return generate_latest()
