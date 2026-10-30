"""A failed model call is never answered by a second generation (Q3 (a), fresh review I1).

The vendor SDKs, under the relaunch policy, send nothing again after a timeout once the
request left. Three callers then sent the whole generation again in another form: the
planner and the ReAct loop called ``ainvoke`` after their streamed call failed, and the
structured output's auto-tool door returned « nothing usable » so the buffered door
generated again. Each now sends another form only when the first generated nothing
(``client_retries.may_send_in_another_form``): a refusal, or a defect off the wire.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from pydantic import BaseModel, Field

from src.domains.agents.services.smart_planner_service import SmartPlannerService
from src.infrastructure.llm.structured_output import _structured_via_auto_tool
from src.infrastructure.llm.structured_output_errors import (
    StructuredOutputCallError,
    StructuredOutputRefusedError,
)

pytestmark = pytest.mark.unit

_REQUEST = httpx.Request("POST", "https://provider.test/v1/chat")


def _timed_out_once_sent() -> BaseException:
    error = openai.APITimeoutError(request=_REQUEST)
    error.__cause__ = httpx.ReadTimeout("slow", request=_REQUEST)
    return error


def _refused() -> BaseException:
    response = httpx.Response(400, request=_REQUEST, json={"error": {"code": 400}})
    return openai.BadRequestError("HTTP 400", response=response, body=None)


class _FailingStream:
    """A model whose streamed call raises; its buffered call answers and is counted."""

    max_retries = 2

    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.ainvoke = AsyncMock(return_value=AIMessageChunk(content='{"steps": []}'))

    async def astream_events(self, _payload: Any, **_kw: Any) -> AsyncIterator[dict[str, Any]]:
        raise self.error
        yield {}  # pragma: no cover - makes this an async generator

    def bind_tools(self, _tools: Any, **_kw: Any) -> _FailingStream:
        return self


def _emit() -> Any:
    return patch(
        "src.infrastructure.llm.reasoning_stream.make_reasoning_emit",
        return_value=lambda _text: None,
    )


# ---------------------------------------------------------------------------
# The planner
# ---------------------------------------------------------------------------


async def test_the_planner_never_generates_again_after_a_timeout_once_sent() -> None:
    llm = _FailingStream(_timed_out_once_sent())

    with _emit(), pytest.raises(openai.APITimeoutError):
        await SmartPlannerService._invoke_planner_streaming_reasoning(
            llm, [HumanMessage(content="my agenda")], config={"callbacks": []}
        )

    llm.ainvoke.assert_not_awaited()


async def test_a_refused_planner_stream_is_answered_by_the_buffered_call() -> None:
    llm = _FailingStream(_refused())

    with _emit():
        await SmartPlannerService._invoke_planner_streaming_reasoning(
            llm, [HumanMessage(content="my agenda")], config={"callbacks": []}
        )

    llm.ainvoke.assert_awaited_once()


# ---------------------------------------------------------------------------
# The ReAct loop
# ---------------------------------------------------------------------------


async def _react_call(llm: _FailingStream) -> Any:
    from src.domains.agents.models import create_initial_state
    from src.domains.agents.nodes import react_nodes as rn
    from src.domains.agents.utils.react_budget import react_turn_reset

    state = create_initial_state(__import__("uuid").uuid4(), session_id="s", run_id="r")
    state["react_system_blocks"] = ["You are LIA."]
    state.update(react_turn_reset())
    state["react_max_iterations_effective"] = 70
    state["messages"] = [HumanMessage(content="Find a restaurant.", id="h1")]
    chat = MagicMock()
    chat.bind_tools = MagicMock(return_value=llm)
    with (
        patch.object(rn, "get_llm", return_value=chat),
        patch.object(rn, "_rebuild_wrapped_tools", return_value=[MagicMock()]),
        _emit(),
    ):
        return await rn.react_call_model_node(state, config={})


async def test_the_react_loop_never_generates_again_after_a_timeout_once_sent() -> None:
    llm = _FailingStream(_timed_out_once_sent())
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="answered twice"))

    with pytest.raises(openai.APITimeoutError):
        await _react_call(llm)

    llm.ainvoke.assert_not_awaited()


async def test_a_refused_react_stream_is_answered_by_the_buffered_call() -> None:
    llm = _FailingStream(_refused())
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="answered", id="a1"))

    await _react_call(llm)

    llm.ainvoke.assert_awaited_once()


# ---------------------------------------------------------------------------
# The structured output's auto-tool door
# ---------------------------------------------------------------------------


class _Verdict(BaseModel):
    answer: str = Field(description="The answer.")


async def test_the_auto_tool_door_does_not_hand_a_timeout_to_the_next_door() -> None:
    """Returning « nothing usable » made the buffered door generate a second time."""
    llm = _FailingStream(_timed_out_once_sent())

    with pytest.raises(StructuredOutputCallError):
        await _structured_via_auto_tool(
            llm=llm,
            messages=[HumanMessage(content="hi")],
            schema=_Verdict,
            reasoning_emit=lambda _text: None,
            provider="openai",
        )


async def test_a_refused_auto_tool_call_leaves_the_next_door_open() -> None:
    llm = _FailingStream(_refused())

    result = await _structured_via_auto_tool(
        llm=llm,
        messages=[HumanMessage(content="hi")],
        schema=_Verdict,
        reasoning_emit=lambda _text: None,
        provider="openai",
    )

    assert result is None


async def test_the_last_door_still_names_a_refusal() -> None:
    llm = _FailingStream(_refused())

    with pytest.raises(StructuredOutputRefusedError):
        await _structured_via_auto_tool(
            llm=llm,
            messages=[HumanMessage(content="hi")],
            schema=_Verdict,
            reasoning_emit=lambda _text: None,
            provider="anthropic",
            last_door=True,
        )
