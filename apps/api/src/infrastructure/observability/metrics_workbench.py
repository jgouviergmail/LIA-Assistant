"""Prometheus metrics of the « Tools » section (ADR-369).

The person acts by hand and is told every outcome on the spot; these series
tell the OPERATOR how the providers behave behind it — a mailbox that keeps
refusing, a calendar that times out, a submission replayed. Every label is a
closed vocabulary: a tool, an operation, a refusal code — never an id or a name.
"""

from prometheus_client import Counter, Histogram

workbench_requests_total = Counter(
    "workbench_requests_total",
    "Provider operations of the Tools section, by outcome",
    # tool: mail | calendar | tasks | contacts | files | lights
    # operation: the route's act (list, read, create, update, delete, send, …)
    # outcome: ok | a workbench refusal code (domains/workbench/errors.py)
    ["tool", "operation", "outcome"],
)

workbench_provider_latency_seconds = Histogram(
    "workbench_provider_latency_seconds",
    "Time a provider took to answer one operation of the Tools section",
    ["tool"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0),
)

workbench_idempotency_replays_total = Counter(
    "workbench_idempotency_replays_total",
    "Submissions made a second time with the same key, answered without a provider call",
    # outcome: done | pending | unknown
    ["tool", "outcome"],
)

workbench_idempotency_unguarded_total = Counter(
    "workbench_idempotency_unguarded_total",
    "Submissions sent without the once-only guard because the cache could not be reached",
    ["tool"],
)
