"""Prometheus metrics of what an executed pipeline plan left behind (ADR-346).

One increment per failed step, under its typed code: a FOR_EACH item counts,
its aggregate never (``diagnostics.failure_context``). It is the one
Prometheus view of a failure that happens BEFORE a tool is called — an
unresolved reference, a refused parameter, an empty template — which no tool
metric and no register row sees.

The label set is closed by construction: ``error_code`` is a ``ToolErrorCode``
member or the ``unclassified`` fallback (a tool's free-form code, or none).
"""

from prometheus_client import Counter

from src.core.field_names import FIELD_ERROR_CODE

pipeline_step_failures_total = Counter(
    "pipeline_step_failures_total",
    "Failed steps of executed pipeline plans, by typed error code",
    [FIELD_ERROR_CODE],
)
