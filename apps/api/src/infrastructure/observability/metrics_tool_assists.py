"""Prometheus metrics of what LIA does from the Tools (ADR-372).

The person is told every outcome on the spot; these series tell the OPERATOR what the clicks cost
in time and how often a model let them down. Every label is a closed vocabulary.
"""

from prometheus_client import Counter, Histogram

tool_assists_total = Counter(
    "tool_assists_total",
    "Assists asked from the Tools, by outcome",
    # assist: a member of ToolAssist (domains/tool_assists/catalogue.py)
    # outcome: ok | held | quota | refused | failed | abandoned
    ["assist", "outcome"],
)

tool_assist_duration_seconds = Histogram(
    "tool_assist_duration_seconds",
    "Time a person waited for one assist, the source's read included",
    ["assist"],
    buckets=(0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0),
)
