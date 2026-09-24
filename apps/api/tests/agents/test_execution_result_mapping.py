"""ExecutionResult → AgentResult: the real mapper, on the real shapes.

Every test here used to build the ``agent_result`` dict BY HAND and assert on
its own copy — ``map_execution_result_to_agent_result`` was never called. The
copy had already drifted: it wrote ``"error"`` where the mapper wrote
``"failed"``, and it re-implemented the aggregation rule it claimed to pin. Six
green tests protected nothing (ADR-303, defect D17).

They now call the mapper. The shapes below are what ``parallel_executor``
really writes: the whole ``UnifiedToolOutput`` envelope
(``{"success", "data", "message"}``), never a pre-flattened payload.
"""

from __future__ import annotations

import pytest

from src.domains.agents.constants import AgentResultStatus
from src.domains.agents.orchestration.mappers import map_execution_result_to_agent_result
from src.domains.agents.orchestration.schemas import ExecutionResult, StepResult

pytestmark = [pytest.mark.unit]

TURN_ID = 1
KEY = f"{TURN_ID}:plan_executor"


def _map(execution_result: ExecutionResult) -> dict:
    return map_execution_result_to_agent_result(
        execution_result=execution_result, plan_id="plan_test", turn_id=TURN_ID
    )[KEY]


def _ok_step(index: int, tool: str, payload: dict) -> StepResult:
    return StepResult(
        step_index=index,
        tool_name=tool,
        args={},
        result={"success": True, "data": payload, "message": "done"},
        success=True,
        execution_time_ms=50,
    )


def _ko_step(index: int, tool: str, error: str, code: str | None = None) -> StepResult:
    return StepResult(
        step_index=index,
        tool_name=tool,
        args={},
        result={"success": False, "error": error, "error_code": code},
        success=False,
        error=error,
        execution_time_ms=10,
    )


class TestExecutionResultToAgentResultMapping:
    """What the mapper publishes, for each shape a plan can end in."""

    def test_a_successful_plan_maps_to_success_with_no_failed_step(self) -> None:
        execution_result = ExecutionResult(
            success=True,
            step_results=[
                _ok_step(
                    0,
                    "search_contacts_tool",
                    {"contacts": [{"name": "John Doe"}], "total_count": 1},
                )
            ],
            total_steps=1,
            completed_steps=1,
            total_execution_time_ms=250,
        )
        agent_result = _map(execution_result)

        assert agent_result["agent_name"] == "plan_executor"
        assert agent_result["status"] == AgentResultStatus.SUCCESS.value
        assert agent_result["error"] is None
        assert agent_result["failed_steps"] == []

    def test_a_totally_failed_plan_maps_to_error_and_keeps_every_failure(self) -> None:
        execution_result = ExecutionResult(
            success=False,
            step_results=[
                _ko_step(0, "search_contacts_tool", "API connection failed", "EXTERNAL_API_ERROR")
            ],
            total_steps=1,
            completed_steps=0,
            failed_step_index=0,
            error="API connection failed",
            total_execution_time_ms=100,
        )
        agent_result = _map(execution_result)

        assert agent_result["status"] == AgentResultStatus.ERROR.value
        assert agent_result["error"] == "API connection failed"
        assert len(agent_result["failed_steps"]) == 1
        assert agent_result["failed_steps"][0]["tool_name"] == "search_contacts_tool"
        assert agent_result["failed_steps"][0]["error_code"] == "EXTERNAL_API_ERROR"

    def test_a_plan_that_never_ran_keeps_its_own_verdict(self) -> None:
        """No step at all: the aggregate cannot be derived from steps."""
        execution_result = ExecutionResult(
            success=False,
            step_results=[],
            total_steps=1,
            completed_steps=0,
            error="Planner produced no executable step",
            total_execution_time_ms=0,
        )
        agent_result = _map(execution_result)

        assert agent_result["status"] == AgentResultStatus.ERROR.value
        assert agent_result["failed_steps"] == []

    def test_a_mixed_plan_is_a_success_that_carries_its_failure(self) -> None:
        """The defect this file failed to catch: a partial plan is not a failure."""
        execution_result = ExecutionResult(
            success=False,  # the legacy all(...) verdict — the mapper no longer reads it
            step_results=[
                _ok_step(0, "search_contacts_tool", {"contacts": [{"name": "Jean"}]}),
                _ko_step(1, "resolve_reference", "VALIDATION_ERROR", "INVALID_INPUT"),
            ],
            total_steps=2,
            completed_steps=1,
            failed_step_index=1,
            error="Step 'resolve_reference' failed",
            total_execution_time_ms=60,
        )
        agent_result = _map(execution_result)

        assert agent_result["status"] == AgentResultStatus.SUCCESS.value
        # The plan's own verdict is KEPT exactly as before ADR-303 — only the
        # STATUS was corrected. The formatter reads `error` in the ERROR branch
        # alone, so a partial plan still says its failures once, through the
        # runtime failures directive fed by failed_steps.
        assert agent_result["error"] == "Step 'resolve_reference' failed"
        assert [f["tool_name"] for f in agent_result["failed_steps"]] == ["resolve_reference"]
        assert agent_result["failed_steps"][0]["error_code"] == "INVALID_INPUT"

    def test_a_free_form_error_code_is_not_typed_but_the_step_is_kept(self) -> None:
        """A code outside the taxonomy degrades to None — the failure remains."""
        execution_result = ExecutionResult(
            success=False,
            step_results=[_ko_step(0, "mcp_tool", "server said no", "SERVER_REFUSED")],
            total_steps=1,
            completed_steps=0,
            failed_step_index=0,
            error="server said no",
            total_execution_time_ms=10,
        )
        agent_result = _map(execution_result)

        assert agent_result["status"] == AgentResultStatus.ERROR.value
        assert agent_result["failed_steps"][0]["error_code"] is None
        assert agent_result["failed_steps"][0]["error"] == "server said no"

    def test_a_step_with_no_result_payload_still_maps(self) -> None:
        """Defensive: a StepResult may carry no dict at all."""
        execution_result = ExecutionResult(
            success=False,
            step_results=[
                StepResult(
                    step_index=0,
                    tool_name="ghost_tool",
                    args={},
                    result=None,
                    success=False,
                    error="no payload",
                )
            ],
            total_steps=1,
            completed_steps=0,
            failed_step_index=0,
            error="no payload",
            total_execution_time_ms=0,
        )
        agent_result = _map(execution_result)

        assert agent_result["status"] == AgentResultStatus.ERROR.value
        assert agent_result["failed_steps"][0]["error"] == "no payload"
        assert agent_result["failed_steps"][0]["error_code"] is None
