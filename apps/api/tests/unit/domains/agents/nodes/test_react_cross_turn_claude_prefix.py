"""Two consecutive frequent ReAct turns on Claude share their history prefix (ADR-362).

The simulation the vendor recommends for finding an invalidator — diff two
consecutive request bodies, cache markers stripped — run on what LIA's own code
builds: the block-windowed history, the frequent turn layout, the real
``ChatAnthropic`` request builder and the Claude payload policy. Claude reads a
prefix back only from an entry written at a breakpoint, so the turn-N request
must end its history on a breakpoint whose whole prefix turn N+1 sends again,
byte for byte, within the API's 20-block lookback.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.domains.agents.nodes.react_history import window_messages_for_react
from src.domains.agents.nodes.react_turn_layout import compose_turn_messages
from src.infrastructure.llm.providers.anthropic_hooks import install_claude_hooks

pytestmark = pytest.mark.unit

STATIC_PROMPT = "You are LIA, a personal assistant.\n" + "A stable rule of the loop.\n" * 40
TOOLS = [
    {"name": name, "description": f"The {name} tool.", "input_schema": {"type": "object"}}
    for name in ("get_events_tool", "get_emails_tool")
]
#: The API checks at most 20 content blocks back from a breakpoint.
LOOKBACK_POSITIONS = 20


def _thread(turns: int) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for turn in range(1, turns + 1):
        messages += [HumanMessage(content=f"question {turn}"), AIMessage(content=f"answer {turn}")]
    return messages


def _system_blocks(turn: int) -> list[str]:
    """The turn's prompt and context: the date and the memories change every turn."""
    return [
        f"{STATIC_PROMPT}{DYNAMIC_CONTEXT_MARKER}\nToday is day {turn}.",
        f"<Memories>memory retrieved for question {turn}</Memories>",
    ]


def _request(turn: int, *, frequent: bool) -> dict[str, Any]:
    """The first ReAct call of ``turn``, as the loop builds and sends it."""
    messages = [*_thread(turn - 1), HumanMessage(content=f"question {turn}")]
    windowed = window_messages_for_react(messages, turn_id=turn, blocks=frequent)
    composed = compose_turn_messages(
        _system_blocks(turn),
        windowed,
        context_after_question=frequent,
        provider="anthropic",
    )
    llm = ChatAnthropic(model="claude-sonnet-5", api_key="sk-test", max_tokens=64)
    install_claude_hooks(llm)
    return llm._get_request_payload(composed, tools=TOOLS)


def _unmarked(value: Any) -> Any:
    """The body as the cache key sees it: markers are not part of the prefix."""
    if isinstance(value, dict):
        return {key: _unmarked(item) for key, item in value.items() if key != "cache_control"}
    if isinstance(value, list):
        return [_unmarked(item) for item in value]
    return value


def _history_end(payload: dict[str, Any]) -> int:
    marked = [
        index
        for index, message in enumerate(payload["messages"])
        if isinstance(message["content"], list)
        and any("cache_control" in block for block in message["content"])
    ]
    assert len(marked) == 1, marked
    return marked[0]


class TestFrequentTurnsOnClaude:
    def test_the_next_turn_resends_the_marked_history_byte_for_byte(self) -> None:
        turn, following = _request(3, frequent=True), _request(4, frequent=True)
        end = _history_end(turn)
        assert _unmarked(turn["tools"]) == _unmarked(following["tools"])
        assert _unmarked(turn["system"]) == _unmarked(following["system"])
        assert _unmarked(turn["messages"][: end + 1]) == _unmarked(following["messages"][: end + 1])

    def test_the_next_turns_read_point_lies_within_the_lookback(self) -> None:
        """Turn N+1 marks its own history end further on: the entry turn N wrote
        is found by walking back over the content BLOCKS between the two."""
        end = _history_end(_request(3, frequent=True))
        following = _request(4, frequent=True)
        between = sum(
            len(message["content"]) if isinstance(message["content"], list) else 1
            for message in following["messages"][end + 1 : _history_end(following) + 1]
        )
        assert 0 < between < LOOKBACK_POSITIONS

    def test_the_turns_own_context_stays_after_the_read_point(self) -> None:
        payload = _request(4, frequent=True)
        question = payload["messages"][_history_end(payload) + 1]
        text = question["content"] if isinstance(question["content"], str) else str(question)
        assert "question 4" in text
        assert "memory retrieved for question 4" in text

    def test_every_breakpoint_fits_the_api_budget(self) -> None:
        payload = _request(4, frequent=True)
        explicit = (
            sum(
                1
                for block in payload["system"]
                if isinstance(block, dict) and "cache_control" in block
            )
            + 1
        )  # the history end
        assert explicit + 1 <= 4  # and the rolling (automatic) breakpoint
        assert payload["cache_control"] == {"type": "ephemeral"}


class TestOccasionalTurnsOnClaude:
    def test_the_turns_context_in_the_system_prompt_ends_the_shared_prefix(self) -> None:
        """Why only frequent turns read their history back: in the occasional
        layout the turn's data closes the system prompt, before the history."""
        turn, following = _request(3, frequent=False), _request(4, frequent=False)
        assert _unmarked(turn["system"]) != _unmarked(following["system"])
