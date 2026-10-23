"""Which earlier thinking a Claude request carries back (ADR-306, ADR-362).

A previous turn's thinking is the vendor's default context on the generations
that keep it, and the API drops, unbilled, a block the receiving model cannot
read. LIA's history is rebuilt every turn, so a generation that BINDS a block to
its conversation would refuse (or drop, with every later block) what it wrote
earlier; a generation that strips prior thinking itself also drops the messages
cache after it. Measured 2026-10-22 on a generation that keeps it without binding
it: the replayed block -- in LIA's history shape, two assistant messages per
ReAct turn -- is accepted and billed as input (H5).
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from src.infrastructure.llm.providers.anthropic_thinking import replay_prior_turn_thinking
from src.infrastructure.observability.metrics_prompt_cache import (
    llm_prior_turn_thinking_blocks_total,
)

pytestmark = pytest.mark.unit

KEEPS = "claude-sonnet-5"  # keeps prior thinking, does not bind it
BINDS = "claude-opus-5-5"  # binds a block to the conversation that produced it
STRIPS = "claude-haiku-4-5"  # the API strips prior thinking itself


def _thinking() -> dict[str, Any]:
    return {"type": "thinking", "thinking": "", "signature": "sig"}


def _answer(model: str | None, *, text: str = "Paris.") -> AIMessage:
    metadata = {"model_name": model} if model else {}
    return AIMessage(
        content=[_thinking(), {"type": "text", "text": text}], response_metadata=metadata
    )


def _turns(*assistant: AIMessage) -> list[BaseMessage]:
    return [
        HumanMessage(content="Capital of France?"),
        *assistant,
        HumanMessage(content="And Italy?"),
    ]


def _blocks(message: BaseMessage) -> list[str]:
    return [block["type"] for block in message.content if isinstance(block, dict)]


class TestTheModelThatWroteItReadsItBack:
    def test_a_generation_that_keeps_prior_thinking_gets_its_own(self) -> None:
        messages = replay_prior_turn_thinking(_turns(_answer(KEEPS)), KEEPS, enabled=True)
        assert _blocks(messages[1]) == ["thinking", "text"]

    def test_a_dated_snapshot_is_the_same_model(self) -> None:
        """The API may answer under the dated name of the alias LIA requested."""
        messages = replay_prior_turn_thinking(
            _turns(_answer("claude-opus-4-5-20251101")), "claude-opus-4-5", enabled=True
        )
        assert _blocks(messages[1]) == ["thinking", "text"]

    def test_an_older_name_starting_the_same_way_is_another_model(self) -> None:
        messages = replay_prior_turn_thinking(
            _turns(_answer("claude-opus-4")), "claude-opus-4-5", enabled=True
        )
        assert _blocks(messages[1]) == ["text"]

    def test_both_assistant_messages_of_a_react_turn_keep_their_own(self) -> None:
        """The loop's final message and the response's, as the history holds them."""
        messages = replay_prior_turn_thinking(
            _turns(_answer(KEEPS), _answer(KEEPS, text="Paris, surely.")), KEEPS, enabled=True
        )
        assert [_blocks(message) for message in messages[1:3]] == [["thinking", "text"]] * 2


class TestEverythingElseIsStripped:
    def test_another_models_thinking_is_not_sent(self) -> None:
        """It would be dropped unread -- and the vendor still calls that drop's
        outcome a rollout: removing it settles the shape."""
        messages = replay_prior_turn_thinking(
            _turns(_answer("claude-opus-5"), _answer(KEEPS)), KEEPS, enabled=True
        )
        assert [_blocks(message) for message in messages[1:3]] == [["text"], ["thinking", "text"]]

    def test_a_generation_that_binds_its_thinking_gets_none_back(self) -> None:
        """Its history changed since (LIA rebuilds it every turn): a 400, or with
        ``drop_block`` the first stale block and EVERY one after it -- the
        current loop's included."""
        messages = replay_prior_turn_thinking(_turns(_answer(BINDS)), BINDS, enabled=True)
        assert _blocks(messages[1]) == ["text"]

    def test_a_generation_that_strips_prior_thinking_gets_none_back(self) -> None:
        """Sent, it would be stripped by the API -- and the cache after it lost."""
        messages = replay_prior_turn_thinking(_turns(_answer(STRIPS)), STRIPS, enabled=True)
        assert _blocks(messages[1]) == ["text"]

    def test_a_block_of_unknown_origin_is_not_sent(self) -> None:
        messages = replay_prior_turn_thinking(_turns(_answer(None)), KEEPS, enabled=True)
        assert _blocks(messages[1]) == ["text"]

    def test_a_generation_the_table_does_not_declare_is_named_as_such(self) -> None:
        """Nothing is known of it, so nothing is sent -- and the operator reads
        « undeclared » (a row to add), never « the API strips it »."""
        later = "claude-unreleased-9"
        counter = llm_prior_turn_thinking_blocks_total.labels(
            model=later, decision="stripped", reason="receiver_undeclared"
        )
        before = counter._value.get()
        messages = replay_prior_turn_thinking(_turns(_answer(later)), later, enabled=True)
        assert _blocks(messages[1]) == ["text"]
        assert counter._value.get() == before + 1

    def test_the_operator_switch_strips_everything(self) -> None:
        messages = replay_prior_turn_thinking(_turns(_answer(KEEPS)), KEEPS, enabled=False)
        assert _blocks(messages[1]) == ["text"]

    def test_redacted_thinking_follows_the_same_rule(self) -> None:
        redacted = AIMessage(
            content=[{"type": "redacted_thinking", "data": "x"}, {"type": "text", "text": "A1"}],
            response_metadata={"model_name": BINDS},
        )
        messages = replay_prior_turn_thinking(_turns(redacted), BINDS, enabled=True)
        assert _blocks(messages[1]) == ["text"]

    def test_a_message_left_with_nothing_is_left_empty_for_the_client_to_drop(self) -> None:
        """``langchain-anthropic`` drops an empty assistant message (the API
        refuses one); the contract test proves it on the real client."""
        bare = AIMessage(content=[_thinking()], response_metadata={"model_name": BINDS})
        messages = replay_prior_turn_thinking(_turns(bare), BINDS, enabled=True)
        assert messages[1].content == []


class TestTheCurrentTurnIsNeverTouched:
    def test_the_tool_loop_in_progress_keeps_its_thinking(self) -> None:
        """A tool loop must replay the thinking of the call it continues."""
        loop = AIMessage(
            content=[_thinking(), {"type": "tool_use", "id": "t1", "name": "a", "input": {}}],
            tool_calls=[{"name": "a", "args": {}, "id": "t1"}],
            response_metadata={"model_name": BINDS},
        )
        messages: list[BaseMessage] = [
            HumanMessage(content="Prepare my day"),
            loop,
            ToolMessage(content="ok", tool_call_id="t1"),
        ]
        assert replay_prior_turn_thinking(messages, BINDS, enabled=True)[1] is loop

    def test_a_tool_result_with_a_text_note_is_not_a_turn_boundary(self) -> None:
        """The client merges the result and the note into ONE user message that
        answers the call: the call's thinking stays."""
        loop = AIMessage(
            content=[_thinking(), {"type": "tool_use", "id": "t1", "name": "a", "input": {}}],
            tool_calls=[{"name": "a", "args": {}, "id": "t1"}],
            response_metadata={"model_name": BINDS},
        )
        messages: list[BaseMessage] = [
            HumanMessage(content="Prepare my day"),
            loop,
            ToolMessage(content="ok", tool_call_id="t1"),
            HumanMessage(content="(approved)"),
        ]
        assert replay_prior_turn_thinking(messages, BINDS, enabled=True)[1] is loop

    def test_a_plain_text_history_is_untouched(self) -> None:
        messages = _turns(AIMessage(content="A1"))
        assert replay_prior_turn_thinking(messages, KEEPS, enabled=True) == messages

    def test_the_messages_given_are_never_mutated(self) -> None:
        answer = _answer(BINDS)
        replay_prior_turn_thinking(_turns(answer), BINDS, enabled=True)
        assert _blocks(answer) == ["thinking", "text"]
