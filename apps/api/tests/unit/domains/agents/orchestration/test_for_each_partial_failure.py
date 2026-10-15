"""A FOR_EACH with failed items keeps its successes, and names each failure (ADR-347).

The aggregate the executor writes under the FOR_EACH step's own id is what the
mapper reads: the items are not plan steps. It merged every item, so the only
``success`` values it met were the failed items' ``False`` — one failure out of
three made the whole aggregate a failure, the mapper dropped it, and the
response never saw the two confirmations nor the two results (probed on the
real functions, 2026-10-14). Now the aggregate is built from the items that
succeeded, carries the failed ones in ``FIELD_FOR_EACH_FAILED_ITEMS``, and is a
failure only when every item failed; the mapper lists one failure per item.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from src.core.field_names import FIELD_FOR_EACH_AGGREGATE, FIELD_FOR_EACH_FAILED_ITEMS
from src.domains.agents.constants import AgentResultStatus
from src.domains.agents.formatters.agent_results import format_agent_results_for_prompt
from src.domains.agents.orchestration.for_each_aggregation import aggregate_for_each_results
from src.domains.agents.orchestration.mappers import (
    build_execution_result,
    map_execution_result_to_agent_result,
)
from src.domains.agents.orchestration.plan_schemas import ExecutionStep, StepType
from src.domains.diagnostics.failure_context import count_failed_steps

pytestmark = pytest.mark.unit

TURN = 7

_OK_A: dict[str, Any] = {"result": "Reminder created for Tuesday", "reminders": [{"id": "a"}]}
_OK_B: dict[str, Any] = {"result": "Reminder created for Saturday", "reminders": [{"id": "b"}]}
_FAILED: dict[str, Any] = {
    "success": False,
    "error": "quota reached",
    "error_code": "RATE_LIMIT_EXCEEDED",
}


def _aggregate(items: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    steps = copy.deepcopy(items)
    aggregate_for_each_results(steps, "step_2", list(items))
    return steps


def _step(step_id: str, tool_name: str) -> ExecutionStep:
    return ExecutionStep(
        step_id=step_id, step_type=StepType.TOOL, agent_name="probe_agent", tool_name=tool_name
    )


def _agent_result(completed_steps: dict[str, dict[str, Any]]) -> dict[str, Any]:
    plan_steps = [_step("step_1", "get_events_tool"), _step("step_2", "create_reminder_tool")]
    mapped = map_execution_result_to_agent_result(
        execution_result=build_execution_result(plan_steps, completed_steps),
        plan_id="plan",
        turn_id=TURN,
    )
    (result,) = mapped.values()
    return result


class TestTheAggregateKeepsTheSuccesses:
    @pytest.mark.parametrize(
        "order",
        [("a", "x", "b"), ("x", "a", "b"), ("a", "b", "x")],
        ids=["failure_between", "failure_first", "failure_last"],
    )
    def test_a_partial_failure_is_a_success_carrying_the_failed_items(
        self, order: tuple[str, str, str]
    ) -> None:
        payloads = {"a": _OK_A, "b": _OK_B, "x": _FAILED}
        items = {f"step_2_item_{i}": payloads[key] for i, key in enumerate(order)}
        failed_id = f"step_2_item_{order.index('x')}"

        aggregate = _aggregate(items)["step_2"]

        assert aggregate.get("success") is not False
        assert "error" not in aggregate
        assert aggregate["result"] == [_OK_A["result"], _OK_B["result"]]
        assert aggregate["reminders"] == [{"id": "a"}, {"id": "b"}]
        assert aggregate[FIELD_FOR_EACH_FAILED_ITEMS] == [
            {"step_id": failed_id, "error": "quota reached", "error_code": "RATE_LIMIT_EXCEEDED"}
        ]
        assert aggregate[FIELD_FOR_EACH_AGGREGATE] is True

    def test_every_item_failed_is_a_failure_naming_each_item(self) -> None:
        items = {
            "step_2_item_0": _FAILED,
            "step_2_item_1": {**_FAILED, "error": "timeout", "error_code": "TIMEOUT"},
        }

        aggregate = _aggregate(items)["step_2"]

        assert aggregate["success"] is False
        assert aggregate["error"] == "quota reached"
        assert aggregate["error_code"] == "RATE_LIMIT_EXCEEDED"
        assert [item["error_code"] for item in aggregate[FIELD_FOR_EACH_FAILED_ITEMS]] == [
            "RATE_LIMIT_EXCEEDED",
            "TIMEOUT",
        ]

    def test_no_failure_adds_no_failure_field(self) -> None:
        aggregate = _aggregate({"step_2_item_0": _OK_A, "step_2_item_1": _OK_B})["step_2"]

        assert FIELD_FOR_EACH_FAILED_ITEMS not in aggregate
        assert aggregate["result"] == [_OK_A["result"], _OK_B["result"]]

    def test_the_directive_still_counts_one_failure_per_item(self) -> None:
        """ADR-346: the aggregate is never a failure of its own."""
        steps = _aggregate({"step_2_item_0": _OK_A, "step_2_item_1": _FAILED})

        assert count_failed_steps(steps) == 1


class TestTheMapperReadsTheItems:
    def test_a_partial_for_each_is_a_success_whose_confirmations_reach_the_answer(
        self,
    ) -> None:
        steps = _aggregate(
            {"step_2_item_0": _OK_A, "step_2_item_1": _FAILED, "step_2_item_2": _OK_B}
        )
        steps["step_1"] = {"result": "2 events found"}

        result = _agent_result(steps)
        summary = format_agent_results_for_prompt({f"{TURN}:plan_executor": result}, TURN)

        assert result["status"] == AgentResultStatus.SUCCESS.value
        assert [(f["tool_name"], f["error_code"]) for f in result["failed_steps"]] == [
            ("create_reminder_tool", "RATE_LIMIT_EXCEEDED")
        ]
        assert _OK_A["result"] in summary
        assert _OK_B["result"] in summary
        assert "quota reached" not in summary

    def test_every_failed_item_is_its_own_failed_step(self) -> None:
        steps = _aggregate(
            {
                "step_2_item_0": _FAILED,
                "step_2_item_1": {**_FAILED, "error_code": "TIMEOUT"},
                "step_2_item_2": _OK_A,
            }
        )

        result = _agent_result(steps)

        assert [f["error_code"] for f in result["failed_steps"]] == [
            "RATE_LIMIT_EXCEEDED",
            "TIMEOUT",
        ]
        assert {f["step_index"] for f in result["failed_steps"]} == {1}

    def test_a_plan_whose_only_step_failed_on_every_item_is_an_error(self) -> None:
        steps = _aggregate({"step_2_item_0": _FAILED, "step_2_item_1": _FAILED})

        result = _agent_result(steps)

        assert result["status"] == AgentResultStatus.ERROR.value
        assert len(result["failed_steps"]) == 2

    def test_another_step_that_ran_keeps_the_plan_a_success(self) -> None:
        steps = _aggregate({"step_2_item_0": _FAILED, "step_2_item_1": _FAILED})
        steps["step_1"] = {"result": "2 events found"}

        result = _agent_result(steps)

        assert result["status"] == AgentResultStatus.SUCCESS.value
        assert len(result["failed_steps"]) == 2


class TestTheExecutionResult:
    """The one conversion both the task orchestrator and the initiative read."""

    def test_it_follows_the_plan_order_and_names_the_first_failure(self) -> None:
        plan_steps = [
            _step("step_1", "get_events_tool"),
            _step("step_2", "create_reminder_tool"),
            _step("step_3", "send_email_tool"),
        ]
        completed = {
            "step_3": {"success": False, "error": "refused", "error_code": "FORBIDDEN"},
            "step_1": {"result": "ok"},
        }

        result = build_execution_result(plan_steps, completed)

        assert [r.tool_name for r in result.step_results] == ["get_events_tool", "send_email_tool"]
        assert [r.step_index for r in result.step_results] == [0, 2]
        assert result.success is False
        assert result.failed_step_index == 1
        assert result.error == "refused"
        assert result.total_steps == 3
        assert result.completed_steps == 2

    def test_a_step_that_stored_no_dict_is_a_success_wrapped_as_data(self) -> None:
        result = build_execution_result([_step("step_1", "get_events_tool")], {"step_1": "text"})

        assert result.success is True
        assert result.step_results[0].result == {"data": "text"}
        assert result.error is None
