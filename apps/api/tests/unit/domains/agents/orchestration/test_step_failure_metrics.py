"""Failed pipeline steps are counted under a bounded, typed label (ADR-346).

The counter is the Prometheus view of a failure that happens BEFORE a tool is
called (an unresolved reference, a refused parameter, an empty template): the
tool metrics never see it, the registers never record it. Its one label must
stay inside the ``ToolErrorCode`` taxonomy, or every tool inventing a code
would mint a new series.
"""

from __future__ import annotations

from typing import Any

import pytest
from prometheus_client import REGISTRY

from src.core.constants import PIPELINE_STEP_FAILURE_UNCLASSIFIED
from src.domains.agents.orchestration.step_failure_metrics import (
    record_pipeline_step_failures,
)
from src.domains.agents.tools.common import ToolErrorCode, ToolErrorModel

pytestmark = [pytest.mark.unit]

_METRIC = "pipeline_step_failures_total"


def _counted(code: str) -> float:
    return REGISTRY.get_sample_value(_METRIC, {"error_code": code}) or 0.0


def _failed(code: str | None) -> dict[str, Any]:
    return {"success": False, "error": "refused", "error_code": code}


def test_each_failed_step_is_counted_once_under_its_typed_code() -> None:
    labels = ("CONNECTOR_NOT_ACTIVATED", "INVALID_INPUT", PIPELINE_STEP_FAILURE_UNCLASSIFIED)
    before = {label: _counted(label) for label in labels}

    recorded = record_pipeline_step_failures(
        {
            "step_1": _failed("CONNECTOR_NOT_ACTIVATED"),
            "step_2": {"success": True},
            "step_3": _failed("INVALID_INPUT"),
            "step_4": _failed("invalid_parameters"),
            "step_5": _failed(None),
        }
    )

    assert recorded == 4
    assert _counted("CONNECTOR_NOT_ACTIVATED") - before["CONNECTOR_NOT_ACTIVATED"] == 1
    assert _counted("INVALID_INPUT") - before["INVALID_INPUT"] == 1
    # A free-form code and a missing one share the bounded fallback label.
    unclassified = _counted(PIPELINE_STEP_FAILURE_UNCLASSIFIED)
    assert unclassified - before[PIPELINE_STEP_FAILURE_UNCLASSIFIED] == 2


def test_a_free_form_code_never_becomes_a_label() -> None:
    record_pipeline_step_failures({"step_1": _failed("tool_invented_this_code")})

    assert REGISTRY.get_sample_value(_METRIC, {"error_code": "tool_invented_this_code"}) is None


def test_a_native_tool_refusal_keeps_its_typed_pipeline_metric_label() -> None:
    payload = ToolErrorModel(code=ToolErrorCode.INVALID_INPUT, message="refused").to_response()
    before = _counted(ToolErrorCode.INVALID_INPUT.value)
    unclassified_before = _counted(PIPELINE_STEP_FAILURE_UNCLASSIFIED)
    assert record_pipeline_step_failures({"step_1": payload}) == 1
    assert _counted(ToolErrorCode.INVALID_INPUT.value) - before == 1
    assert _counted(PIPELINE_STEP_FAILURE_UNCLASSIFIED) == unclassified_before


@pytest.mark.parametrize(
    "completed_steps",
    [None, {}, {"step_1": "garbage"}, {"step_1": {"success": True}}],
    ids=["none", "empty", "malformed", "clean"],
)
def test_nothing_to_count_counts_nothing(completed_steps: dict[str, Any] | None) -> None:
    assert record_pipeline_step_failures(completed_steps) == 0
