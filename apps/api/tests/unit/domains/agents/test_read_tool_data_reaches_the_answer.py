"""A read tool's data reaches the pipeline's answer, end to end (ADR-347).

The defect was fixed three times, tool by tool, because each link between a
tool's ``structured_data`` and the response prompt was owned by a different
module and none of them saw the whole road. This file walks the road with the
real functions, link by link — the executor's tool call, the merge into
``completed_steps``, the FOR_EACH aggregate, the rebuilt ``ExecutionResult``,
the mapper, the state the orchestrator persists, and the response chain the
model is handed — so a regression in any one of them breaks it here.

Measured 2026-10-14 on three model families: without the data block, 0 of 9
answers gave the durations a route matrix had computed; with it, 27 of 27.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from src.core.field_names import FIELD_TOOL_DATA
from src.domains.agents.nodes.response_node import _build_response_chain
from src.domains.agents.orchestration import parallel_executor as pe
from src.domains.agents.orchestration import tool_data_projection as projection
from src.domains.agents.orchestration.for_each_aggregation import aggregate_for_each_results
from src.domains.agents.orchestration.mappers import (
    build_execution_result,
    map_execution_result_to_agent_result,
)
from src.domains.agents.orchestration.plan_schemas import ExecutionStep, StepType
from src.domains.agents.orchestration.tool_data_projection import (
    previous_turns_without_tool_data,
    without_tool_data,
)
from src.domains.agents.registry.catalogue import CostProfile, PermissionProfile, ToolManifest
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.react_tool_wrapper import compose_tool_message

pytestmark = pytest.mark.unit

TURN = 9

_MANIFEST = ToolManifest(
    name="get_route_matrix_tool",
    agent="route_agent",
    description="test",
    parameters=[],
    outputs=[],
    cost=CostProfile(),
    permissions=PermissionProfile(),
    mutation_policy="read",
)


def _matrix(origin: str, minutes: tuple[int, int]) -> UnifiedToolOutput:
    """A route matrix as the tool returns it: the durations live in structured_data."""
    return UnifiedToolOutput.data_success(
        message=f"Route matrix from {origin}: 2 destinations.",
        structured_data={
            "origin": origin,
            "rows": [
                {"destination": "Le Comptoir", "duration_minutes": minutes[0]},
                {"destination": "La Fontaine", "duration_minutes": minutes[1]},
            ],
        },
    )


async def _run_step(step_id: str, output: UnifiedToolOutput, share: int = 1) -> pe.StepResult:
    """The executor's own tool call, then the StepResult its tool step builds."""

    async def _coroutine(**kwargs: Any) -> UnifiedToolOutput:
        return output

    tool = SimpleNamespace(coroutine=_coroutine, args_schema=None, name=_MANIFEST.name)
    with (
        patch.object(
            pe.ToolRegistry, "get_instance", return_value=SimpleNamespace(get_tool=lambda n: tool)
        ),
        patch.object(pe, "_build_tool_runtime", side_effect=lambda t, a, c, s: a),
    ):
        executed = await pe._execute_tool(
            tool_name=_MANIFEST.name,
            args={},
            config={"configurable": {}},
            store=None,
            manifest=_MANIFEST,
            data_share=share,
        )
    return pe.StepResult(
        step_id=step_id,
        step_type=StepType.TOOL,
        tool_name=_MANIFEST.name,
        result=executed.result,
        success=True,
    )


def _plan_step(step_id: str) -> ExecutionStep:
    return ExecutionStep(
        step_id=step_id, step_type=StepType.TOOL, agent_name="route_agent", tool_name=_MANIFEST.name
    )


def _prompt_text(agent_results: dict[str, Any], summary: str = "") -> str:
    """Everything the response model is handed, rendered as the provider receives it."""
    chain = _build_response_chain(
        base_system_prompt="BASE",
        agent_results_summary=summary,
        skills_context="",
        plan_rejection_reason=None,
        state={"messages": [], "agent_results": agent_results, "current_turn_id": TURN},
        user_language="en",
        llm=FakeListChatModel(responses=["ok"]),
        performed_actions_block="",
    )
    rendered = chain.first.format_messages(messages=[])
    return "\n".join(str(message.content) for message in rendered)


@pytest.fixture(autouse=True)
def _response_budget() -> Any:
    with (
        patch.object(projection, "slot_tool_result_budget", return_value=4_000),
        patch(
            "src.domains.agents.formatters.tool_data.slot_tool_result_budget", return_value=4_000
        ),
    ):
        yield


class TestTheRoad:
    async def test_a_read_step_s_data_reaches_the_response_model(self) -> None:
        completed: dict[str, dict[str, Any]] = {}
        pe._merge_single_step_result(
            completed, await _run_step("step_1", _matrix("home", (14, 15)))
        )

        agent_results = map_execution_result_to_agent_result(
            execution_result=build_execution_result([_plan_step("step_1")], completed),
            plan_id="p",
            turn_id=TURN,
        )
        prompt = _prompt_text(agent_results)

        assert '"duration_minutes": 14' in prompt
        assert '"duration_minutes": 15' in prompt
        assert "TOOL DATA" in prompt and "<external_content" in prompt

    async def test_every_item_of_a_loop_reaches_it(self) -> None:
        completed: dict[str, dict[str, Any]] = {}
        for index, (origin, minutes) in enumerate((("home", (14, 15)), ("office", (31, 9)))):
            step = await _run_step(f"step_1_item_{index}", _matrix(origin, minutes), share=2)
            pe._merge_single_step_result(completed, step)
        aggregate_for_each_results(completed, "step_1", ["step_1_item_0", "step_1_item_1"])

        agent_results = map_execution_result_to_agent_result(
            execution_result=build_execution_result([_plan_step("step_1")], completed),
            plan_id="p",
            turn_id=TURN,
        )
        prompt = _prompt_text(agent_results)

        assert '"origin": "home"' in prompt and '"origin": "office"' in prompt
        assert '"duration_minutes": 31' in prompt

    async def test_the_answer_s_own_words_stay_free_of_data(self) -> None:
        """A confirmed draft's fast path shows the SUMMARY: it never holds a block."""
        completed: dict[str, dict[str, Any]] = {}
        pe._merge_single_step_result(
            completed, await _run_step("step_1", _matrix("home", (14, 15)))
        )
        agent_results = map_execution_result_to_agent_result(
            execution_result=build_execution_result([_plan_step("step_1")], completed),
            plan_id="p",
            turn_id=TURN,
        )

        prompt = _prompt_text(agent_results, summary="Event created")

        assert prompt.index("Event created") < prompt.index("TOOL DATA")

    async def test_the_persisted_state_carries_no_block(self) -> None:
        completed: dict[str, dict[str, Any]] = {}
        pe._merge_single_step_result(
            completed, await _run_step("step_1", _matrix("home", (14, 15)))
        )
        agent_results = map_execution_result_to_agent_result(
            execution_result=build_execution_result([_plan_step("step_1")], completed),
            plan_id="p",
            turn_id=TURN,
        )

        persisted = without_tool_data(completed)["step_1"]
        assert isinstance(persisted, dict)
        assert FIELD_TOOL_DATA not in persisted
        next_turn = previous_turns_without_tool_data(agent_results, TURN + 1)
        assert "TOOL DATA" not in _prompt_text(next_turn)


class TestBothModesReadTheSameData:
    async def test_the_pipeline_block_is_the_react_block(self) -> None:
        output = _matrix("home", (14, 15))
        completed: dict[str, dict[str, Any]] = {}
        pe._merge_single_step_result(completed, await _run_step("step_1", output))
        (record,) = completed["step_1"][FIELD_TOOL_DATA]

        react = compose_tool_message(output, tool_name=_MANIFEST.name, budget_tokens=4_000)

        assert record["text"] in react
