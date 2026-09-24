"""The Claude request payload policy — what makes the prompt cache pay (ADR-306).

Measured on the Claude API on 2026-09-23 with the real ``response`` prompt on
Sonnet 5 (``max_tokens=0``, input billed only):

* ONE system block, split at the dynamic marker: the second call READ 5,074
  cached tokens and wrote 88;
* TWO system blocks (every turn that carries agent results — langchain merges
  consecutive system messages into a list): the second call read 0 and
  REWROTE 5,222 tokens at 1.25x, because the breakpoint sat on the last,
  dynamic block.

And on Opus 5.5, a thinking block from an earlier turn replayed under the
system prompt LIA rebuilds every turn: 400 « bound to a different
conversation » once enforcement is on (every account created from 2026-08-31),
25 extra billed input tokens when it is not.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.infrastructure.llm.providers.anthropic_payload import (
    mark_static_system_prefix,
    shape_claude_payload,
    strip_prior_turn_thinking,
    wants_rolling_breakpoint,
)

pytestmark = pytest.mark.unit

CC = {"type": "ephemeral"}
STATIC = "You are LIA.\nStatic rules."
DYNAMIC = f"{DYNAMIC_CONTEXT_MARKER} (all variable data below) ---\nDate: 2026-09-23 13:07"


def _text(text: str, **extra: Any) -> dict[str, Any]:
    return {"type": "text", "text": text, **extra}


class TestTheStaticPrefixIsMarkedWhateverTheShape:
    def test_a_single_prompt_is_split_at_the_marker(self) -> None:
        assert mark_static_system_prefix(f"{STATIC}\n\n{DYNAMIC}") == [
            _text(STATIC, cache_control=CC),
            _text(DYNAMIC),
        ]

    def test_a_list_of_blocks_is_split_where_the_marker_is_not_at_its_end(self) -> None:
        """The measured defect: the breakpoint belongs after the static text,
        never on the last block — which is the turn's data."""
        results = _text("CURRENT TURN DATA: 3 emails")
        assert mark_static_system_prefix([_text(f"{STATIC}\n{DYNAMIC}"), results]) == [
            _text(STATIC, cache_control=CC),
            _text(DYNAMIC),
            results,
        ]

    def test_a_constant_block_before_the_prompt_joins_the_cached_prefix(self) -> None:
        """The auto-tool directive precedes the prompt: it is static, cached with it."""
        directive = _text("Respond by calling the `Plan` tool.")
        assert mark_static_system_prefix([directive, _text(f"{STATIC}\n{DYNAMIC}")]) == [
            directive,
            _text(STATIC, cache_control=CC),
            _text(DYNAMIC),
        ]

    def test_a_marker_opening_a_block_ends_the_prefix_on_the_previous_one(self) -> None:
        assert mark_static_system_prefix([_text(STATIC), _text(DYNAMIC)]) == [
            _text(STATIC, cache_control=CC),
            _text(DYNAMIC),
        ]

    def test_a_prompt_without_the_marker_is_left_alone(self) -> None:
        """Without the marker nothing says where the per-request content starts:
        a breakpoint there would pay the write premium on every call."""
        assert mark_static_system_prefix(STATIC) == STATIC
        blocks = [_text(STATIC), _text("more")]
        assert mark_static_system_prefix(blocks) == blocks

    def test_nothing_before_the_marker_means_nothing_to_cache(self) -> None:
        assert mark_static_system_prefix(DYNAMIC) == DYNAMIC
        assert mark_static_system_prefix(f"   \n{DYNAMIC}") == f"   \n{DYNAMIC}"

    def test_breakpoints_a_caller_placed_are_kept_as_they_are(self) -> None:
        blocks = [_text(STATIC, cache_control=CC), _text(DYNAMIC)]
        assert mark_static_system_prefix(blocks) == blocks

    def test_no_system_prompt_is_not_an_error(self) -> None:
        assert mark_static_system_prefix(None) is None
        assert mark_static_system_prefix([]) == []


def _user(text: str) -> dict[str, Any]:
    return {"role": "user", "content": [_text(text)]}


def _tool_result(call_id: str) -> dict[str, Any]:
    return {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": call_id, "content": "ok"}],
    }


def _thinking() -> dict[str, Any]:
    return {"type": "thinking", "thinking": "", "signature": "sig"}


class TestTheRollingBreakpointOnlyWhereItIsRead:
    def test_a_single_call_writes_no_rolling_entry(self) -> None:
        """Its tail (the date, the question, the history) is unique: written at
        1.25x, read by nobody."""
        assert wants_rolling_breakpoint({"messages": [_user("Hi")]}) is False

    def test_structured_output_with_its_one_schema_tool_is_a_single_call(self) -> None:
        payload = {"messages": [_user("Plan")], "tools": [{"name": "Plan"}]}
        assert wants_rolling_breakpoint(payload) is False

    def test_an_agent_offered_several_tools_will_loop(self) -> None:
        payload = {"messages": [_user("Prepare my day")], "tools": [{"name": "a"}, {"name": "b"}]}
        assert wants_rolling_breakpoint(payload) is True

    def test_a_tool_round_trip_is_a_loop_whatever_the_tool_count(self) -> None:
        payload = {
            "messages": [
                _user("Prepare my day"),
                {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "a"}]},
                _tool_result("t1"),
            ],
            "tools": [{"name": "a"}],
        }
        assert wants_rolling_breakpoint(payload) is True


class TestPriorTurnThinkingIsNotReplayed:
    def test_a_previous_turns_thinking_is_removed_its_answer_kept(self) -> None:
        answer = _text("Paris.")
        messages = [
            _user("Capital of France?"),
            {"role": "assistant", "content": [_thinking(), answer]},
            _user("And Italy?"),
        ]
        assert strip_prior_turn_thinking(messages) == [
            _user("Capital of France?"),
            {"role": "assistant", "content": [answer]},
            _user("And Italy?"),
        ]

    def test_the_current_tool_loop_keeps_its_thinking_verbatim(self) -> None:
        """A tool loop must replay the thinking of the call it continues."""
        current = [
            _user("Prepare my day"),
            {
                "role": "assistant",
                "content": [_thinking(), {"type": "tool_use", "id": "t1", "name": "a"}],
            },
            _tool_result("t1"),
        ]
        assert strip_prior_turn_thinking(current) == current

    def test_a_user_message_carrying_tool_results_is_not_a_turn_boundary(self) -> None:
        """Results plus a text note still answer the assistant call before them."""
        messages = [
            _user("Prepare my day"),
            {
                "role": "assistant",
                "content": [_thinking(), {"type": "tool_use", "id": "t1", "name": "a"}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": "ok"},
                    _text("(approved)"),
                ],
            },
        ]
        assert strip_prior_turn_thinking(messages) == messages

    def test_redacted_thinking_goes_too(self) -> None:
        messages = [
            _user("Q1"),
            {
                "role": "assistant",
                "content": [{"type": "redacted_thinking", "data": "x"}, _text("A1")],
            },
            _user("Q2"),
        ]
        assert strip_prior_turn_thinking(messages)[1] == {
            "role": "assistant",
            "content": [_text("A1")],
        }

    def test_an_assistant_turn_left_empty_is_dropped(self) -> None:
        """An empty content is a 400; two user messages in a row are merged by the API."""
        messages = [_user("Q1"), {"role": "assistant", "content": [_thinking()]}, _user("Q2")]
        assert strip_prior_turn_thinking(messages) == [_user("Q1"), _user("Q2")]

    def test_a_plain_text_history_is_untouched(self) -> None:
        messages = [_user("Q1"), {"role": "assistant", "content": "A1"}, _user("Q2")]
        assert strip_prior_turn_thinking(messages) == messages


class TestTheWholePolicy:
    def test_a_single_call_marks_its_static_prefix_and_nothing_else(self) -> None:
        payload = shape_claude_payload(
            {"system": [_text(f"{STATIC}\n{DYNAMIC}"), _text("DATA")], "messages": [_user("Hi")]}
        )
        assert "cache_control" not in payload
        assert payload["system"][0] == _text(STATIC, cache_control=CC)

    def test_a_tool_loop_also_gets_the_rolling_entry(self) -> None:
        payload = shape_claude_payload(
            {
                "system": f"{STATIC}\n{DYNAMIC}",
                "messages": [_user("Go"), _tool_result("t1")],
                "tools": [{"name": "a"}, {"name": "b"}],
            }
        )
        assert payload["cache_control"] == CC

    def test_the_rolling_entry_is_withheld_at_four_explicit_breakpoints(self) -> None:
        """Automatic + four explicit breakpoints is a documented 400."""
        marked = [_text(f"block {i}", cache_control=CC) for i in range(4)]
        payload = shape_claude_payload(
            {"system": marked, "messages": [_user("Go"), _tool_result("t1")]}
        )
        assert "cache_control" not in payload

    def test_a_breakpoint_on_a_tool_counts_toward_the_four(self) -> None:
        marked = [_text(f"block {i}", cache_control=CC) for i in range(3)]
        payload = shape_claude_payload(
            {
                "system": marked,
                "messages": [_user("Go"), _tool_result("t1")],
                "tools": [{"name": "a", "cache_control": CC}, {"name": "b"}],
            }
        )
        assert "cache_control" not in payload

    def test_an_empty_payload_is_not_an_error(self) -> None:
        assert shape_claude_payload({}) == {}

    def test_every_breakpoint_written_is_the_five_minute_one(self) -> None:
        """The write surcharge is priced at the 5-minute rate alone
        (``PROMPT_CACHE_WRITE_MULTIPLIER``): a ``ttl`` here would make every
        written token cost 2x while the ledger books 1.25x."""
        payload = shape_claude_payload(
            {
                "system": [_text(f"{STATIC}\n{DYNAMIC}"), _text("DATA")],
                "messages": [_user("Go"), _tool_result("t1")],
                "tools": [{"name": "a"}, {"name": "b"}],
            }
        )
        written = [payload["cache_control"]] + [
            block["cache_control"] for block in payload["system"] if "cache_control" in block
        ]
        assert written and all(breakpoint == {"type": "ephemeral"} for breakpoint in written)
