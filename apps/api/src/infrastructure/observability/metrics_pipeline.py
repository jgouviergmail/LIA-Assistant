"""Prometheus metrics of what an executed pipeline plan left behind (ADR-346, ADR-347).

``pipeline_step_failures_total``: one increment per failed step, under its
typed code: a FOR_EACH item counts, its aggregate never
(``diagnostics.failure_context``). It is the one Prometheus view of a failure
that happens BEFORE a tool is called — an unresolved reference, a refused
parameter, an empty template — which no tool metric and no register row sees.

The label set is closed by construction: ``error_code`` is a ``ToolErrorCode``
member or the ``unclassified`` fallback (a tool's free-form code, or none).

``pipeline_tool_data_truncated_total``: the data blocks of the plan's read steps
that a response prompt carried incomplete. ``tool_name`` comes from the plan's
catalogue, the bound the ReAct twin (``react_tool_result_truncated_total``)
already rests on; ``reason`` is ``cut`` or ``dropped``.
"""

from prometheus_client import Counter

from src.core.field_names import FIELD_ERROR_CODE, FIELD_TOOL_NAME

pipeline_step_failures_total = Counter(
    "pipeline_step_failures_total",
    "Failed steps of executed pipeline plans, by typed error code",
    [FIELD_ERROR_CODE],
)

pipeline_tool_data_truncated_total = Counter(
    "pipeline_tool_data_truncated_total",
    "Pipeline data blocks a response prompt carried incomplete (ADR-347), counted when "
    "the prompt is assembled: 'cut' when the projection paged a block at an item "
    "boundary, 'dropped' when the section left a block out to stay within the response "
    "slot's budget. Both are stated to the model. A steady rate on one tool means its "
    "data outgrows the budget.",
    [FIELD_TOOL_NAME, "reason"],
)
