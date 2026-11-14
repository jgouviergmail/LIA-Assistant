"""The token-counting bench times the real middleware and counts what it encodes (lot 26)."""

from __future__ import annotations

import pytest
import tiktoken
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from scripts.agents.measure_history_token_counting import history, measure_once, memo_chars

pytestmark = pytest.mark.unit


def test_a_history_is_a_browser_agents_rounds() -> None:
    messages = history(rounds=3, snapshot_chars=500)

    assert isinstance(messages[0], SystemMessage) and len(messages) == 2 + 2 * 3
    calls = [m for m in messages if isinstance(m, AIMessage)]
    results = [m for m in messages if isinstance(m, ToolMessage)]
    assert [c.tool_calls[0]["id"] for c in calls] == [r.tool_call_id for r in results]
    assert all(len(str(r.content)) >= 500 for r in results)


def test_one_call_counts_its_encodes_and_restores_the_encoder() -> None:
    original = tiktoken.Encoding.encode
    messages = history(rounds=2, snapshot_chars=300)

    measured = measure_once(messages, max_tokens=None)

    assert measured["encodes"] >= len(messages) and measured["chars"] > 0
    assert tiktoken.Encoding.encode is original


def test_a_memo_encodes_the_newest_round_only() -> None:
    messages = history(rounds=4, snapshot_chars=1000)

    assert memo_chars(messages) == sum(len(str(m.content)) for m in messages[-2:])
    assert memo_chars(messages) < sum(len(str(m.content)) for m in messages) / 3
