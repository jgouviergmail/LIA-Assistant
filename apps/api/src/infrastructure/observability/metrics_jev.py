"""Decision routing and added latency; fixed registry labels, never user content."""

from prometheus_client import Counter, Histogram

jev_decisions_total = Counter(
    "jev_decisions_total",
    "Native decisions by integration point and actual outcome.",
    ["usage", "outcome"],
)
jev_decision_duration_seconds = Histogram(
    "jev_decision_duration_seconds",
    "Decision policy, provider and accounting duration.",
    ["usage", "outcome"],
    buckets=(0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 5, 10),
)
