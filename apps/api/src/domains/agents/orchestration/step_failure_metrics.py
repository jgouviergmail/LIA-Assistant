"""Failed pipeline steps, counted under a bounded typed label (ADR-346).

The orchestrator calls this once per executed plan. The step results are read
through the honesty directive's own predicate (``diagnostics.failure_context``),
so the count is what the model is told: one per failed step, a FOR_EACH item
counted and its aggregate never. The label is a ``ToolErrorCode`` member or the
``unclassified`` fallback — a tool's free-form code never mints a series.
"""

from __future__ import annotations

from typing import Any

from src.core.constants import PIPELINE_STEP_FAILURE_UNCLASSIFIED
from src.domains.agents.tools.common import coerce_tool_error_code
from src.domains.diagnostics.failure_context import failed_step_codes
from src.infrastructure.observability.metrics_pipeline import pipeline_step_failures_total


def record_pipeline_step_failures(completed_steps: dict[str, Any] | None) -> int:
    """Count every failed step of an executed plan under its typed code.

    Args:
        completed_steps: The executor's step results, or None; an entry that is
            not a step dict is skipped, never raised on.

    Returns:
        How many failed steps were counted.
    """
    codes = failed_step_codes(completed_steps)
    for code in codes:
        member = coerce_tool_error_code(code)
        label = member.value if member is not None else PIPELINE_STEP_FAILURE_UNCLASSIFIED
        pipeline_step_failures_total.labels(error_code=label).inc()
    return len(codes)
