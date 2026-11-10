"""Decision routing and added latency; fixed registry labels, never user content."""

from prometheus_client import Counter, Histogram

jev_decisions_total = Counter(
    "jev_decisions_total",
    "Native decisions by integration point and actual outcome.",
    ["usage", "outcome"],
)
#: The durable statistics (ADR-374): rows the per-worker flush wrote, and the flushes
#: that failed — ``statements`` keeps its batch for the next flush, ``commit`` (outcome
#: unknown) drops it rather than count it twice.
jev_statistics_rows_total = Counter(
    "jev_statistics_rows_total",
    "JEV daily statistics rows written (inserted or incremented) by the per-worker flush.",
)
jev_statistics_flush_failures_total = Counter(
    "jev_statistics_flush_failures_total",
    "JEV statistics flushes that failed, by the stage that failed.",
    ["stage"],
)
jev_decision_duration_seconds = Histogram(
    "jev_decision_duration_seconds",
    "Decision policy, provider and accounting duration.",
    ["usage", "outcome"],
    buckets=(0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 5, 10),
)
