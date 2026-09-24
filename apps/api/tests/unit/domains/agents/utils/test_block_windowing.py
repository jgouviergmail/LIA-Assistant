"""History windowed by blocks, anchored on the turn counter (ADR-309, amended 2026-09-24).

A window of the last N turns slides by one turn on EVERY turn, so the history's
first message changes every time and no provider's prompt cache can read the
history again. Dropped by blocks, the window holds between N and N + block - 1
turns and its first message only moves when a whole block goes: between two
drops each turn's history is the previous one plus the last turn.

The blocks were first aligned on the thread's LENGTH — and the messages reducer
shortens the thread from its head as a long turn's tool results arrive, so each
trim moved the boundary in the middle of a turn (production, 2026-09-24: three
calls of one routine run re-billed after the tools). They are now counted from
the END, by the conversation's turn counter alone, and in whole turns.
"""

from __future__ import annotations

import math
import random
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from src.core.config import settings
from src.domains.agents.utils.message_windowing import (
    block_window_turns,
    get_block_windowed_messages,
    history_block_turns,
)

pytestmark = pytest.mark.unit

WINDOW = 5
BLOCK = 3


def _turns(count: int) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for turn in range(1, count + 1):
        messages += [HumanMessage(content=f"q{turn}"), AIMessage(content=f"a{turn}")]
    return messages


def _tool_turns(count: int) -> list[BaseMessage]:
    """Turns as the state holds them: question, tool call, tool result, answer."""
    messages: list[BaseMessage] = []
    for turn in range(1, count + 1):
        messages += [
            HumanMessage(content=f"q{turn}", id=f"h{turn}"),
            AIMessage(
                content="", id=f"c{turn}", tool_calls=[{"id": f"k{turn}", "name": "t", "args": {}}]
            ),
            ToolMessage(content="result", tool_call_id=f"k{turn}", id=f"r{turn}"),
            AIMessage(content=f"a{turn}", id=f"a{turn}"),
        ]
    return messages


def _window(messages: list[BaseMessage], turn_id: int | None) -> list[BaseMessage]:
    return get_block_windowed_messages(
        messages, window_size=WINDOW, block_size=BLOCK, turn_id=turn_id
    )


def _first(messages: list[BaseMessage]) -> str:
    return str(messages[0].content)


def _count_turns(messages: list[BaseMessage]) -> int:
    return sum(isinstance(message, HumanMessage) for message in messages)


def _conversation(messages: list[BaseMessage]) -> list[BaseMessage]:
    return [message for message in messages if not isinstance(message, SystemMessage)]


class TestTheBlocks:
    """A thread that still holds every previous turn: turn T follows T - 1 of them."""

    def test_the_first_message_holds_between_two_drops(self) -> None:
        firsts = [_first(_window(_turns(total), turn_id=total + 1)) for total in range(6, 12)]

        assert firsts == ["q1", "q1", "q4", "q4", "q4", "q7"]

    def test_the_window_holds_between_n_and_n_plus_block_minus_one_turns(self) -> None:
        sizes = {_count_turns(_window(_turns(total), turn_id=total + 1)) for total in range(6, 40)}

        assert sizes == {WINDOW, WINDOW + 1, WINDOW + BLOCK - 1}

    def test_each_turn_extends_the_previous_history_until_a_drop(self) -> None:
        before = _window(_turns(9), turn_id=10)
        after = _window(_turns(10), turn_id=11)

        assert after[: len(before)] == before

    def test_a_short_history_is_kept_whole(self) -> None:
        assert len(_window(_turns(4), turn_id=5)) == 8

    @pytest.mark.parametrize(
        ("window", "block"), [(w, b) for w in range(1, 9) for b in range(1, w + 1)]
    )
    def test_it_keeps_what_the_length_aligned_blocks_kept_on_an_untrimmed_thread(
        self, window: int, block: int
    ) -> None:
        # The blocks it replaces kept W + ((n - W) mod B) of n > W previous turns.
        for previous in range(0, 40):
            expected = previous if previous <= window else window + (previous - window) % block
            kept = get_block_windowed_messages(
                _turns(previous), window_size=window, block_size=block, turn_id=previous + 1
            )
            assert _count_turns(kept) == expected, (window, block, previous)


class TestTheAnchor:
    """The defect: a trimmed head moved the window in the middle of a turn."""

    def test_a_head_trim_that_leaves_the_kept_turns_moves_nothing(self) -> None:
        thread = _tool_turns(30)
        reference = _window(thread, turn_id=31)
        kept_from = thread.index(reference[0])

        for trimmed in range(0, kept_from + 1):  # every cut point, mid-turn ones included
            assert _window(thread[trimmed:], turn_id=31) == reference, trimmed

    def test_within_a_turn_the_counter_does_not_move_so_nothing_does(self) -> None:
        # Every call of one turn reads the same counter, whatever the thread's length.
        thread = _tool_turns(30)
        views = {tuple(m.id for m in _window(thread[cut:], turn_id=31)) for cut in range(0, 60)}

        assert len(views) == 1

    def test_the_next_turn_extends_the_view_through_the_last_answer(self) -> None:
        thread = _tool_turns(30)
        this_turn = _window(thread[:-4], turn_id=30)  # turn 30: 29 previous turns
        next_turn = _window(thread[7:], turn_id=31)  # turn 31, head trimmed meanwhile

        assert next_turn[: len(this_turn)] == this_turn

    def test_without_a_counter_it_slides_by_whole_turns(self) -> None:
        windowed = _window(_turns(9), turn_id=None)

        assert _first(windowed) == "q5"
        assert _count_turns(windowed) == WINDOW


class TestWholeTurns:
    """A turn is kept from its question: the history never opens on an orphan answer."""

    def test_an_answer_whose_question_was_trimmed_never_opens_the_window(self) -> None:
        thread = _turns(12)[1:]  # the reducer cut q1 and kept a1
        windowed = _window(thread, turn_id=13)

        assert isinstance(windowed[0], HumanMessage)

    def test_a_turn_with_several_answers_is_kept_whole(self) -> None:
        # A notification after an answer, then a question that got no answer.
        thread = [*_turns(8), AIMessage(content="notice"), HumanMessage(content="q9")]
        windowed = _window(thread, turn_id=10)

        assert [str(m.content) for m in windowed[-3:]] == ["a8", "notice", "q9"]
        assert _first(windowed) == "q4"

    def test_a_conversation_lia_opened_keeps_its_first_message_while_short(self) -> None:
        opened = [AIMessage(content="LIA speaks first"), *_turns(2)]

        assert _first(_window(opened, turn_id=3)) == "LIA speaks first"

    def test_tool_traffic_and_system_messages_keep_their_old_treatment(self) -> None:
        summary = SystemMessage(content="[summary]")
        windowed = _window([summary, *_tool_turns(8)], turn_id=9)

        assert windowed[0] is summary
        assert not [m for m in windowed if isinstance(m, ToolMessage)]
        assert not [m for m in windowed if isinstance(m, AIMessage) and m.tool_calls]


class TestTrimmedIntoTheBlock:
    """The reducer left fewer turns than the block keeps: the window proper holds."""

    def test_it_keeps_the_window_proper(self) -> None:
        # Turn 13 keeps W + 1 = 6 turns; only 5 and an orphan answer are left.
        assert block_window_turns(WINDOW, BLOCK, 13) == WINDOW + 1
        thread = _turns(11)[11:]  # a6 (orphan), then q7..a11

        windowed = _window(thread, turn_id=13)

        assert _first(windowed) == "q7"
        assert _count_turns(windowed) == WINDOW

    def test_a_further_trim_does_not_move_it_while_it_holds(self) -> None:
        # Turn 14 keeps W + 2 = 7 turns; 6 are left, then 5, the window proper holds.
        assert block_window_turns(WINDOW, BLOCK, 14) == WINDOW + 2
        thread = _turns(11)[9:]  # a5 (orphan), then q6..a11
        views = {
            tuple(str(m.content) for m in _window(thread[cut:], turn_id=14)) for cut in range(4)
        }

        assert views == {tuple(f"{kind}{turn}" for turn in range(7, 12) for kind in "qa")}

    def test_a_history_shorter_than_the_window_is_kept_whole(self) -> None:
        thread = _turns(11)[15:]  # a8 (orphan) then q9..a11

        assert [str(m.content) for m in _window(thread, turn_id=12)][:2] == ["a8", "q9"]


class TestTheCompactionSummary:
    """Compaction appends its summary after what it preserved; the view reads it first."""

    def test_only_the_trim_that_takes_it_changes_the_view(self) -> None:
        summary = SystemMessage(content="[summary]", id="sum")
        thread = _tool_turns(12)
        thread.insert(12, summary)  # after turn 3, where compaction left it
        reference = _window(thread, turn_id=13)

        assert reference[0] is summary
        for cut in range(13):
            assert _window(thread[cut:], turn_id=13) == reference, cut
        assert _window(thread[13:], turn_id=13) == reference[1:]


class TestTheLog:
    def test_it_states_the_turns_wanted_available_and_kept(self) -> None:
        # Turn 14 wants 7 turns; the reducer left 6 (and an orphan answer).
        with patch("src.domains.agents.utils.message_windowing.logger") as logger:
            _window(_turns(11)[9:], turn_id=14)

        (event,), fields = logger.info.call_args
        assert event == "message_windowing_complete"
        assert (fields["turn_id"], fields["turns_wanted"]) == (14, 7)
        assert (fields["turns_available"], fields["turns_kept"]) == (6, WINDOW)


class TestTheCount:
    def test_it_stays_between_the_window_and_the_window_plus_a_block_minus_one(self) -> None:
        assert {block_window_turns(WINDOW, BLOCK, turn) for turn in range(0, 60)} == {5, 6, 7}

    def test_it_grows_by_one_turn_per_turn_then_drops_a_block(self) -> None:
        for turn in range(1, 60):
            before = block_window_turns(WINDOW, BLOCK, turn)
            after = block_window_turns(WINDOW, BLOCK, turn + 1)
            assert after == before + 1 or (before == WINDOW + BLOCK - 1 and after == WINDOW)

    @pytest.mark.parametrize("block", [0, 1])
    def test_a_block_of_one_turn_slides(self, block: int) -> None:
        assert block_window_turns(WINDOW, block, 17) == WINDOW


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


def _random_thread(rng: random.Random, turns: int) -> list[BaseMessage]:
    """A thread with the irregularities production writes into a state."""
    messages: list[BaseMessage] = []
    for turn in range(1, turns + 1):
        messages.append(HumanMessage(content=f"q{turn}", id=f"h{turn}"))
        for call in range(rng.randint(0, 3)):
            messages.append(
                AIMessage(
                    content="",
                    id=f"c{turn}.{call}",
                    tool_calls=[{"id": f"k{turn}.{call}", "name": "t", "args": {}}],
                )
            )
            messages.append(
                ToolMessage(content="r", tool_call_id=f"k{turn}.{call}", id=f"r{turn}.{call}")
            )
        shape = rng.random()
        if shape < 0.8:
            messages.append(AIMessage(content=f"a{turn}", id=f"a{turn}"))
        elif shape < 0.9:  # an answer, then a notification before the next question
            messages.append(AIMessage(content=f"a{turn}", id=f"a{turn}"))
            messages.append(AIMessage(content=f"n{turn}", id=f"n{turn}"))
        # else: a question that never got an answer (an error, an interrupted turn)
    if messages and rng.random() < 0.3:
        # Compaction APPENDS its summary after the messages it preserved; the
        # reducer protects a SystemMessage at index 0 only.
        messages.insert(rng.randint(0, len(messages)), SystemMessage(content="[summary]", id="sum"))
    return messages


class TestPropertiesOverRandomThreads:
    """Seeded, so a failure reproduces; 400 threads, every head trim of each."""

    @pytest.mark.parametrize("seed", range(8))
    def test_the_view_is_a_function_of_the_counter_and_the_kept_turns(self, seed: int) -> None:
        rng = random.Random(seed)
        for _ in range(50):
            thread = _random_thread(rng, rng.randint(0, 25))
            turn_id = rng.randint(1, 60)
            keep = block_window_turns(WINDOW, BLOCK, turn_id)
            reference = _window(thread, turn_id)
            conversational = _conversation(reference)
            questions = _count_turns(thread)

            # The kept conversation is the thread's own, in its order.
            positions = [thread.index(m) for m in conversational]
            assert positions == sorted(positions)
            # Whole turns, from a question, once the history outnumbers the window.
            if questions >= WINDOW:
                assert isinstance(conversational[0], HumanMessage)
                assert _count_turns(conversational) in {keep, WINDOW}
            # Every head trim that leaves the kept turns in place keeps them; the
            # whole view holds while the trim leaves the summary too.
            if questions >= keep and conversational:
                summary_at = next(
                    (i for i, m in enumerate(thread) if isinstance(m, SystemMessage)), None
                )
                for cut in range(1, thread.index(conversational[0]) + 1):
                    view = _window(thread[cut:], turn_id)
                    assert _conversation(view) == conversational, (seed, cut)
                    if summary_at is None or cut <= summary_at:
                        assert view == reference, (seed, cut)
