"""Prometheus metrics of the self-diagnostics subsystem (observe the observer).

Label sets are closed by construction: ``check_id`` comes from the static
check registry, ``status`` from the four-value CheckStatus enum, ``source``
and ``severity`` from the incidents' closed vocabularies — cardinality is
bounded and known.
"""

from prometheus_client import Counter, Histogram

diagnostics_checks_total = Counter(
    "diagnostics_checks_total",
    "Self-check results by check and verdict",
    ["check_id", "status"],
)

diagnostics_self_check_duration_seconds = Histogram(
    "diagnostics_self_check_duration_seconds",
    "Duration of one full self-check tick (engine + persistence)",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

diagnostics_incidents_total = Counter(
    "diagnostics_incidents_total",
    "Incidents opened, by source and severity",
    ["source", "severity"],
)

diagnostics_llm_cost_usd_total = Counter(
    "diagnostics_llm_cost_usd_total",
    "Cumulative USD cost of diagnosis LLM calls",
)

diagnostics_catalogue_miss_total = Counter(
    "diagnostics_catalogue_miss_total",
    "Requests for a query the curated catalogue could not serve (escalation signal, spec §3)",
    ["surface"],
)
