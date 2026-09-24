"""The turn's exchange rhythm drives the three effects together (ADR-311).

One value, published into the turn's state by the router, decides for the whole
turn: the tools the setup binds (every tool, or the relevance selection), where
each call places the turn's context, and whether the history drops by blocks.
Measured on 396 real turns (ADR-308), the context after the question pays only
when every tool is bound, and the history blocks only when the prefix before
them is read again — so none of the three is worth having alone.

The instance setting is never read here: it only supplies the default of an
account that never chose (``users.exchange_rhythm``), upstream of the router.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from src.core.config import settings
from src.domains.agents.nodes import react_nodes as rn
from src.domains.agents.nodes.react_history import window_messages_for_react
from src.domains.agents.utils.message_windowing import get_windowed_messages

pytestmark = pytest.mark.unit


def _setup_state(rhythm: str | None) -> dict[str, Any]:
    state: dict[str, Any] = {"messages": [], "query_intelligence": {"domains": ["event"]}}
    if rhythm is not None:
        state["exchange_rhythm"] = rhythm
    return state


@pytest.mark.parametrize(
    ("rhythm", "every_tool"), [("frequent", True), ("occasional", False), (None, False)]
)
async def test_the_setup_binds_by_the_turn_s_rhythm(
    monkeypatch: pytest.MonkeyPatch, rhythm: str | None, every_tool: bool
) -> None:
    monkeypatch.setattr(rn.settings, "react_agent_enabled", True, raising=False)
    monkeypatch.setattr(rn.settings, "journals_enabled", False, raising=False)
    monkeypatch.setattr(rn.settings, "skills_enabled", False, raising=False)
    # The instance default says the opposite of the turn: the turn wins.
    monkeypatch.setattr(settings, "react_cross_turn_cache_enabled", not every_tool)
    selector = MagicMock()
    selector.select.return_value = ([], {})

    with patch.object(rn, "ReactToolSelector", return_value=selector):
        await rn.react_setup_node(_setup_state(rhythm), {"configurable": {}})

    selector.select.assert_called_once()
    assert selector.select.call_args.kwargs["every_tool"] is every_tool


def _turns(count: int) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for turn in range(1, count + 1):
        messages += [HumanMessage(content=f"q{turn}"), AIMessage(content=f"a{turn}")]
    return messages


def test_without_blocks_the_history_slides_as_the_pipeline_s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "react_agent_history_window_turns", 5)
    history = _turns(11)

    windowed = window_messages_for_react([*history, HumanMessage(content="now")], turn_id=12)

    assert windowed[:-1] == get_windowed_messages(history, window_size=5)
