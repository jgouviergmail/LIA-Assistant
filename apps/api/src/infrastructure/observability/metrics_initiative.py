"""Metrics of the post-execution initiative node (ADR-062).

Read by dashboard 13. A labelled counter that never fired exposes no series, so the
panels reading these carry ``or vector(0)``.
"""

from prometheus_client import Counter, Histogram

initiative_evaluations_total = Counter(
    "initiative_evaluations_total",
    "Initiative phase evaluations",
    ["decision"],  # "act" | "skip"
)

initiative_actions_executed_total = Counter(
    "initiative_actions_executed_total", "Initiative actions executed", ["tool_name"]
)

# Audit 2026-08-19 lot 0: prod showed decision=act evaluations with zero
# executions and only a logger.warning to explain the gap.
initiative_actions_rejected_total = Counter(
    "initiative_actions_rejected_total",
    "Initiative actions rejected by the read-only validation",
    ["reason"],  # non_readonly | duplicate | over_cap
)

initiative_duration_seconds = Histogram(
    "initiative_duration_seconds",
    "Initiative phase total duration",
    buckets=[0.1, 0.5, 1.0, 2.0, 3.0, 5.0],
)

# UXR Lot 4 (A2): tappable follow-up chips emitted under assistant answers.
initiative_followups_total = Counter(
    "initiative_followups_total",
    "Follow-up suggestions emitted by the initiative node",
)
