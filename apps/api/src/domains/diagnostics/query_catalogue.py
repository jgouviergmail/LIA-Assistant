"""The named-query catalogue: the ONLY producer of PromQL in the subsystem.

Free-form query languages never reach a telemetry backend (spec §5, pillar 1):
an LLM or an admin picks a query by key and supplies bounded parameters; this
module renders the PromQL, clamping out-of-bounds values (ADR-184 repair
doctrine — what is mechanically repairable is repaired, never reported).

Every metric a query references is DECLARED on the query:

- ``lia_metrics`` — names this codebase registers; a CI test resolves each one
  against the live prometheus_client registry, so a renamed metric breaks the
  build, not the dashboardless admin at 2 a.m.;
- ``external_metrics`` — exporter-owned names, each carried by
  ``EXTERNAL_METRICS_ALLOWLIST`` with a written reason (audit rule: exclusions
  require a rationale).

``assert_query_catalogue_completeness`` runs at boot (flag on): a query that
uses an undeclared placeholder or metric refuses to start the app rather than
failing at query time (ADR-085 doctrine).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Exporter-owned metric names this catalogue may reference, each with the
#: reason it cannot be resolved against our own registry.
EXTERNAL_METRICS_ALLOWLIST: dict[str, str] = {
    "up": "Synthesised by Prometheus itself for every scrape target.",
    "node_filesystem_avail_bytes": "Produced by node-exporter (host disk telemetry).",
    "node_filesystem_size_bytes": "Produced by node-exporter (host disk telemetry).",
    "node_memory_MemAvailable_bytes": "Produced by node-exporter (host memory telemetry).",
    "node_memory_MemTotal_bytes": "Produced by node-exporter (host memory telemetry).",
}

#: Tokens that look metric-shaped inside templates but are PromQL functions,
#: label names or placeholder names — never metric references.
_NON_METRIC_TOKENS: frozenset[str] = frozenset(
    {
        "histogram_quantile",
        "clamp_min",
        "error_type",
        "job_name",
        "window_minutes",
        "label_replace",
    }
)

_PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")
_METRIC_TOKEN_RE = re.compile(r"\b([a-z][a-zA-Z0-9]*(?:_[a-zA-Z0-9]+)+)\b")


@dataclass(frozen=True)
class QueryParam:
    """A bounded numeric parameter of a named query (published to callers)."""

    name: str
    min_value: float
    max_value: float
    default: float


@dataclass(frozen=True)
class NamedQuery:
    """One curated PromQL query with declared metrics and bounded params."""

    query_id: str
    title: str
    promql_template: str
    params: tuple[QueryParam, ...]
    unit: str
    lia_metrics: tuple[str, ...]
    external_metrics: tuple[str, ...]


_WINDOW = QueryParam(name="window_minutes", min_value=1, max_value=1440, default=15)

QUERY_CATALOGUE: dict[str, NamedQuery] = {
    query.query_id: query
    for query in (
        NamedQuery(
            query_id="api_error_rate",
            title="HTTP 5xx rate",
            promql_template=(
                '100 * sum(rate(http_requests_total{status=~"5.."}[{window_minutes}m]))'
                " / clamp_min(sum(rate(http_requests_total[{window_minutes}m])), 1e-9)"
            ),
            params=(_WINDOW,),
            unit="percent",
            lia_metrics=("http_requests_total",),
            external_metrics=(),
        ),
        NamedQuery(
            query_id="api_latency_p95",
            title="HTTP p95 latency",
            promql_template=(
                "histogram_quantile(0.95, sum(rate("
                "http_request_duration_seconds_bucket[{window_minutes}m])) by (le))"
            ),
            params=(_WINDOW,),
            unit="seconds",
            lia_metrics=("http_request_duration_seconds_bucket",),
            external_metrics=(),
        ),
        NamedQuery(
            query_id="http_request_rate",
            title="HTTP request rate",
            promql_template="sum(rate(http_requests_total[{window_minutes}m]))",
            params=(_WINDOW,),
            unit="rps",
            lia_metrics=("http_requests_total",),
            external_metrics=(),
        ),
        NamedQuery(
            query_id="llm_failure_rate",
            title="LLM API failure rate",
            promql_template=(
                "100 * sum(rate(llm_api_errors_total[{window_minutes}m]))"
                " / clamp_min(sum(rate(llm_api_calls_total[{window_minutes}m])), 1e-9)"
            ),
            params=(_WINDOW,),
            unit="percent",
            lia_metrics=("llm_api_errors_total", "llm_api_calls_total"),
            external_metrics=(),
        ),
        NamedQuery(
            query_id="llm_errors_by_kind",
            title="LLM API errors by kind",
            promql_template=(
                "sum by (error_type) (increase(llm_api_errors_total[{window_minutes}m]))"
            ),
            params=(_WINDOW,),
            unit="count",
            lia_metrics=("llm_api_errors_total",),
            external_metrics=(),
        ),
        NamedQuery(
            query_id="background_job_errors",
            title="Background job errors by job",
            promql_template=(
                "sum by (job_name) (increase(background_job_errors_total[{window_minutes}m]))"
            ),
            params=(_WINDOW,),
            unit="count",
            lia_metrics=("background_job_errors_total",),
            external_metrics=(),
        ),
        NamedQuery(
            query_id="dependency_up",
            title="Scrape-target availability",
            promql_template="up",
            params=(),
            unit="bool",
            lia_metrics=(),
            external_metrics=("up",),
        ),
        NamedQuery(
            query_id="disk_usage_percent",
            title="Host disk usage",
            promql_template=(
                '100 * (1 - (node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"}'
                ' / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"}))'
            ),
            params=(),
            unit="percent",
            lia_metrics=(),
            external_metrics=("node_filesystem_avail_bytes", "node_filesystem_size_bytes"),
        ),
        NamedQuery(
            query_id="memory_usage_percent",
            title="Host memory usage",
            promql_template=(
                "100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))"
            ),
            params=(),
            unit="percent",
            lia_metrics=(),
            external_metrics=("node_memory_MemAvailable_bytes", "node_memory_MemTotal_bytes"),
        ),
        NamedQuery(
            query_id="circuit_breakers_open",
            title="Circuit-breaker states by service",
            promql_template="max by (service) (circuit_breaker_state)",
            params=(),
            unit="state",
            lia_metrics=("circuit_breaker_state",),
            external_metrics=(),
        ),
    )
}


def assert_query_catalogue_completeness(
    catalogue: dict[str, NamedQuery] | None = None,
) -> None:
    """Refuse to run with a structurally broken catalogue (boot assert).

    Args:
        catalogue: Override for tests; defaults to the real catalogue.

    Raises:
        AssertionError: Undeclared placeholder, unbounded param, declared
            metric absent from its template, or a metric-shaped token that is
            neither declared nor allowlisted.
    """
    for key, query in (catalogue if catalogue is not None else QUERY_CATALOGUE).items():
        assert key == query.query_id, f"catalogue key '{key}' != query.query_id '{query.query_id}'"
        _assert_params_and_placeholders(query)
        _assert_declared_metrics(query)


def _assert_params_and_placeholders(query: NamedQuery) -> None:
    """Params bounded and every template placeholder declared.

    Args:
        query: The catalogue entry under validation.

    Raises:
        AssertionError: Unbounded default or undeclared placeholder.
    """
    declared_params = {param.name for param in query.params}
    for param in query.params:
        assert (
            param.min_value <= param.default <= param.max_value
        ), f"{query.query_id}: param '{param.name}' default outside [min, max]"
    placeholders = set(_PLACEHOLDER_RE.findall(query.promql_template))
    undeclared = placeholders - declared_params
    assert not undeclared, f"{query.query_id}: undeclared placeholders {sorted(undeclared)}"


def _assert_declared_metrics(query: NamedQuery) -> None:
    """Every metric referenced ⊆ declared ∪ allowlist, and declarations live.

    Args:
        query: The catalogue entry under validation.

    Raises:
        AssertionError: Stale declaration, unlisted external, or a
            metric-shaped token neither declared nor allowlisted.
    """
    declared_params = {param.name for param in query.params}
    declared_metrics = set(query.lia_metrics) | set(query.external_metrics)
    for metric in declared_metrics:
        assert (
            metric in query.promql_template
        ), f"{query.query_id}: declares metric '{metric}' its template never references"
    for external in query.external_metrics:
        assert (
            external in EXTERNAL_METRICS_ALLOWLIST
        ), f"{query.query_id}: external metric '{external}' missing from the allowlist"
    for token in _METRIC_TOKEN_RE.findall(query.promql_template):
        if token in _NON_METRIC_TOKENS or token in declared_params:
            continue
        assert (
            token in declared_metrics or token in EXTERNAL_METRICS_ALLOWLIST
        ), f"{query.query_id}: metric-shaped token '{token}' is neither declared nor allowlisted"
    # 'up' has no underscore so the token regex cannot see it; the
    # declared-in-template assertion above already covers it.


def render_query(query_id: str, **params: float) -> str:
    """Render a catalogue query, clamping every parameter into its bounds.

    Args:
        query_id: Catalogue identifier.
        **params: Parameter values by name; missing ones use their default,
            unknown ones are ignored (the catalogue is the authority).

    Returns:
        The rendered PromQL string.

    Raises:
        KeyError: Unknown catalogue key (callers translate for their surface).
    """
    query = QUERY_CATALOGUE[query_id]
    values: dict[str, int] = {}
    for param in query.params:
        raw = params.get(param.name, param.default)
        clamped = min(max(float(raw), param.min_value), param.max_value)
        values[param.name] = int(clamped)
    rendered = query.promql_template
    for name, value in values.items():
        rendered = rendered.replace("{" + name + "}", str(value))
    return rendered
