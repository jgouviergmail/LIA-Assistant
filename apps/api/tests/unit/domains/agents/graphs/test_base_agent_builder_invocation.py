"""Per-invocation correctness of build_generic_agent (audit N-183).

Two defects reproduced here:

(a) ``{current_datetime}`` was rendered ONCE at agent build time while built
    agents are cached for the process lifetime — after any uptime, every
    domain agent reasons with a stale "now".

(b) ``create_agent_wrapper_node`` re-recorded the ``usage_metadata`` of EVERY
    AIMessage present in the returned state on EVERY invocation. Since the
    full conversation state is passed in (and returned), turn N re-recorded
    turns 1..N-1 too: token accounting grew quadratically with conversation
    length (same defect for the Prometheus per-tool counters).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool

from src.core.context import current_tracker
from src.domains.agents.graphs.base_agent_builder import (
    build_generic_agent,
    create_agent_wrapper_node,
)


@tool
def _noop_tool(query: str) -> str:
    """Test tool that echoes its input."""
    return query


# Module-level capture store: BaseChatModel is a pydantic model, so class
# attributes would become fields — a plain module global stays out of its way.
_captured_prompts: list[list[BaseMessage]] = []


class _CapturingChatModel(BaseChatModel):
    """Fake chat model capturing every prompt it receives."""

    def _generate(
        self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs
    ) -> ChatResult:
        _captured_prompts.append(list(messages))
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok"))])

    def bind_tools(self, tools: Any, **kwargs: Any) -> _CapturingChatModel:
        return self

    @property
    def _llm_type(self) -> str:
        return "capturing-fake"


class _FakeTracker:
    """Minimal TrackingContext double accumulating record_node_tokens calls."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    async def record_node_tokens(self, **kwargs: Any) -> None:
        self.records.append(kwargs)


@pytest.mark.asyncio
async def test_current_datetime_is_rendered_per_invocation() -> None:
    """The system prompt datetime must be the INVOCATION time, not build time."""
    clock = {"value": "BUILD-TIME"}

    def fake_datetime() -> str:
        return clock["value"]

    config = {
        "agent_name": "contacts_agent",
        "tools": [_noop_tool],
        "system_prompt": "You are the contacts agent. Current datetime: {current_datetime}.",
        "llm_config": {"model": "fake-model"},
        "enable_hitl": False,
        "datetime_generator": fake_datetime,
    }

    _captured_prompts.clear()
    with patch(
        "src.domains.agents.graphs.base_agent_builder.get_llm",
        return_value=_CapturingChatModel(),
    ):
        agent = build_generic_agent(config)

    # Simulate process uptime: the clock has moved since the agent was built.
    clock["value"] = "INVOKE-TIME"

    await agent.ainvoke({"messages": [HumanMessage(content="hello")]})

    assert _captured_prompts, "the model never received a prompt"
    system_text = str(_captured_prompts[0][0].content)
    assert (
        "BUILD-TIME" not in system_text
    ), "system prompt datetime is frozen at agent BUILD time (stale after uptime)"
    assert "INVOKE-TIME" in system_text, "invocation-time datetime missing from system prompt"
    assert "{current_datetime}" not in system_text, "placeholder left unrendered"


@pytest.mark.asyncio
async def test_wrapper_records_only_new_messages_per_invocation() -> None:
    """Across a 5-turn conversation, each turn's usage is recorded exactly once."""
    tracker = _FakeTracker()
    fake_agent = AsyncMock()
    node = create_agent_wrapper_node(fake_agent, "contact_agent", "contact_agent")

    per_turn_tokens = 110  # 100 input + 10 output per NEW assistant message
    history: list[BaseMessage] = []

    token = current_tracker.set(tracker)
    try:
        for turn in range(5):
            history = history + [HumanMessage(content=f"question {turn}")]
            new_ai = AIMessage(
                content=f"answer {turn}",
                usage_metadata={
                    "input_tokens": 100,
                    "output_tokens": 10,
                    "total_tokens": per_turn_tokens,
                },
            )
            fake_agent.ainvoke = AsyncMock(return_value={"messages": history + [new_ai]})

            await node({"messages": history}, config={})

            history = history + [new_ai]
    finally:
        current_tracker.reset(token)

    # Linear accounting: exactly ONE record per turn...
    assert len(tracker.records) == 5, (
        f"expected 5 usage records for 5 turns, got {len(tracker.records)} "
        "(previous turns re-recorded on every invocation — quadratic cost)"
    )
    # ...and the summed tokens equal the real consumption (5 × one message).
    total_recorded = sum(
        record["prompt_tokens"] + record["completion_tokens"] for record in tracker.records
    )
    assert total_recorded == 5 * per_turn_tokens


@pytest.mark.asyncio
async def test_wrapper_still_records_multiple_new_messages_of_one_invocation() -> None:
    """A single invocation producing several LLM calls records each of them."""
    tracker = _FakeTracker()
    fake_agent = AsyncMock()
    node = create_agent_wrapper_node(fake_agent, "contact_agent", "contact_agent")

    entry = [HumanMessage(content="question")]
    new_messages = [
        AIMessage(
            content="",
            tool_calls=[{"id": "c1", "name": "_noop_tool", "args": {}, "type": "tool_call"}],
            usage_metadata={"input_tokens": 50, "output_tokens": 5, "total_tokens": 55},
        ),
        AIMessage(
            content="final",
            usage_metadata={"input_tokens": 60, "output_tokens": 6, "total_tokens": 66},
        ),
    ]
    fake_agent.ainvoke = AsyncMock(return_value={"messages": entry + new_messages})

    token = current_tracker.set(tracker)
    try:
        await node({"messages": entry}, config={})
    finally:
        current_tracker.reset(token)

    assert len(tracker.records) == 2
    assert sum(r["prompt_tokens"] + r["completion_tokens"] for r in tracker.records) == 55 + 66
