"""History windowed by blocks: a prefix that stays the same from turn to turn (ADR-309).

A window of the last N turns slides by one turn on EVERY turn, so the history's
first message changes every time and no provider's prompt cache can read the
history again. Dropped by blocks, the window holds between N and N + block - 1
turns and its first message only moves when a whole block goes: between two
drops each turn's history is the previous one plus the last turn.
"""

from __future__ import annotations

import math

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from src.core.config import settings
from src.domains.agents.utils.message_windowing import (
    get_windowed_messages,
    history_block_turns,
)

pytestmark = pytest.mark.unit


def _turns(count: int) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for turn in range(1, count + 1):
        messages += [HumanMessage(content=f"q{turn}"), AIMessage(content=f"a{turn}")]
    return messages


def _first(messages: list[BaseMessage]) -> str:
    return str(messages[0].content)


class TestTheBlocks:
    def test_the_first_message_holds_between_two_drops(self) -> None:
        firsts = [
            _first(get_windowed_messages(_turns(total), window_size=5, block_size=3))
            for total in range(6, 12)
        ]

        assert firsts == ["q1", "q1", "q4", "q4", "q4", "q7"]

    def test_the_window_holds_between_n_and_n_plus_block_minus_one_turns(self) -> None:
        sizes = {
            len(get_windowed_messages(_turns(total), window_size=5, block_size=3)) // 2
            for total in range(6, 40)
        }

        assert sizes == {5, 6, 7}

    def test_each_turn_extends_the_previous_history_until_a_drop(self) -> None:
        before = get_windowed_messages(_turns(9), window_size=5, block_size=3)
        after = get_windowed_messages(_turns(10), window_size=5, block_size=3)

        assert after[: len(before)] == before

    def test_a_short_history_is_kept_whole(self) -> None:
        assert len(get_windowed_messages(_turns(4), window_size=5, block_size=3)) == 8

    @pytest.mark.parametrize("block", [None, 1])
    def test_without_blocks_the_window_slides_as_before(self, block: int | None) -> None:
        windowed = get_windowed_messages(_turns(9), window_size=5, block_size=block)

        assert _first(windowed) == "q5"
        assert len(windowed) == 10


class TestTheBlockSize:
    def test_it_is_the_configured_share_of_the_window(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "react_cross_turn_history_block_fraction", 0.5)

        assert history_block_turns(5) == 3
        assert history_block_turns(10) == 5

    def test_a_whole_window_share_drops_a_window_at_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "react_cross_turn_history_block_fraction", 1.0)

        assert history_block_turns(5) == 5

    def test_it_never_falls_under_one_turn(self) -> None:
        fraction = settings.react_cross_turn_history_block_fraction
        assert history_block_turns(1) == max(1, math.ceil(fraction))
