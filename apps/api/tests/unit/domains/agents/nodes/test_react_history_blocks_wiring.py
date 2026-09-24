"""Under the cross-turn cache flag, the ReAct loop's history is dropped by blocks (ADR-309).

Sliding by one turn on every turn, the loop's history never gave a provider's
prompt cache a prefix to read again. Under ``REACT_CROSS_TURN_CACHE_ENABLED`` the
loop drops its oldest turns by blocks; without it, nothing changes.

The response node keeps sliding in every mode: its conversation follows the
turn's own context (the query, the date, the agent results), so no provider can
read it back from a cache — blocks would only add up to ``block - 1`` turns of
tokens for nothing.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from src.core.config import settings
from src.domains.agents.nodes.react_history import window_messages_for_react
from src.domains.agents.nodes.response_node import _prepare_conversational_messages

pytestmark = pytest.mark.unit


def _turns(count: int) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for turn in range(1, count + 1):
        messages += [HumanMessage(content=f"q{turn}"), AIMessage(content=f"a{turn}")]
    return messages


@pytest.fixture
def _windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "react_agent_history_window_turns", 5)
    monkeypatch.setattr(settings, "response_message_window_size", 5)
    monkeypatch.setattr(settings, "react_cross_turn_history_block_fraction", 0.5)


def _loop_firsts() -> list[str]:
    return [
        str(window_messages_for_react([*_turns(total), HumanMessage(content="now")])[0].content)
        for total in range(6, 12)
    ]


async def _response_firsts(execution_mode: str) -> list[str]:
    firsts = []
    for total in range(6, 12):
        state = {
            "messages": [*_turns(total), HumanMessage(content="now")],
            "execution_mode": execution_mode,
        }
        messages = await _prepare_conversational_messages(
            state,  # type: ignore[arg-type]
            "run",
            neutralize_history_formatting=False,
            plan_rejection_reason=None,
            current_turn_attachments=None,
            last_user_message="now",
            has_vision_content=False,
        )
        firsts.append(str(messages[0].content))
    return firsts


@pytest.mark.usefixtures("_windows")
class TestTheLoop:
    def test_under_the_flag_its_history_is_dropped_by_blocks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "react_cross_turn_cache_enabled", True)

        assert _loop_firsts() == ["q1", "q1", "q4", "q4", "q4", "q7"]

    def test_without_the_flag_it_slides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "react_cross_turn_cache_enabled", False)

        assert _loop_firsts() == ["q2", "q3", "q4", "q5", "q6", "q7"]


@pytest.mark.usefixtures("_windows")
class TestTheResponse:
    @pytest.mark.parametrize("execution_mode", ["react", "pipeline"])
    async def test_it_slides_even_under_the_flag(
        self, monkeypatch: pytest.MonkeyPatch, execution_mode: str
    ) -> None:
        monkeypatch.setattr(settings, "react_cross_turn_cache_enabled", True)

        # The response windows by message count, so the oldest kept message is an
        # answer; what matters is that it moves by one turn on every turn.
        assert await _response_firsts(execution_mode) == ["a2", "a3", "a4", "a5", "a6", "a7"]
