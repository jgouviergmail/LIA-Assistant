"""The Claude request payload policy — what makes the prompt cache pay (ADR-306).

Measured on the Claude API on 2026-09-23 with the real ``response`` prompt on
Sonnet 5 (``max_tokens=0``, input billed only):

* ONE system block, split at the dynamic marker: the second call READ 5,074
  cached tokens and wrote 88;
* TWO system blocks (every turn that carries agent results — langchain merges
  consecutive system messages into a list): the second call read 0 and
  REWROTE 5,222 tokens at 1.25x, because the breakpoint sat on the last,
  dynamic block.

Which earlier thinking a request carries back is decided before the client
formats it: ``test_anthropic_thinking.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.infrastructure.llm.providers.anthropic_payload import (
    mark_static_system_prefix,
    shape_claude_payload,
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


def _assistant(*blocks: dict[str, Any]) -> dict[str, Any]:
    return {"role": "assistant", "content": list(blocks)}


def _tool_use(call_id: str) -> dict[str, Any]:
    return {"type": "tool_use", "id": call_id, "name": "a", "input": {}}


def _loop(*messages: dict[str, Any]) -> dict[str, Any]:
    """A tool-loop request: several tools offered, the rolling breakpoint applies."""
    return {
        "system": f"{STATIC}\n{DYNAMIC}",
        "messages": list(messages),
        "tools": [{"name": "a"}, {"name": "b"}],
    }


def _marked(message: dict[str, Any]) -> list[dict[str, Any]]:
    content = message["content"]
    return [block for block in content if isinstance(block, dict) and "cache_control" in block]


class TestTheHistoryEndIsAReadPoint:
    """The next turn reads the history back only from an entry written at its end (ADR-362).

    Claude writes an entry only at a breakpoint and a later request finds only
    an entry that exists. In a tool loop the rolling breakpoint sits on the
    turn's tail -- the question with its context, which the next turn never
    sends again -- so without this read point no entry ever ended where the
    next turn's prefix diverges, and the whole history was re-written every
    turn. It costs nothing: the rolling breakpoint already writes the span.
    """

    def test_the_block_before_the_question_is_marked_in_a_tool_loop(self) -> None:
        answer = _assistant(_text("Paris."))
        payload = shape_claude_payload(_loop(_user("Capital of France?"), answer, _user("Go")))
        assert _marked(payload["messages"][1]) == [_text("Paris.", cache_control=CC)]
        assert payload["cache_control"] == CC

    def test_a_plain_text_answer_becomes_a_marked_block(self) -> None:
        payload = shape_claude_payload(
            _loop(_user("Q1"), {"role": "assistant", "content": "A1"}, _user("Q2"))
        )
        assert payload["messages"][1]["content"] == [_text("A1", cache_control=CC)]

    def test_every_text_content_takes_one_shape_in_a_tool_loop(self) -> None:
        """The end becomes a block list the turn it is marked; one turn later it
        is not the end any more. Every text content takes the block shape, so
        the next turn resends the same BYTES (the two-turn simulation in
        ``test_react_cross_turn_claude_prefix`` found the difference)."""
        payload = shape_claude_payload(
            _loop(
                {"role": "user", "content": "Q1"},
                {"role": "assistant", "content": "A1"},
                {"role": "user", "content": "Q2"},
            )
        )
        assert [message["content"] for message in payload["messages"]] == [
            [_text("Q1")],
            [_text("A1", cache_control=CC)],
            [_text("Q2")],
        ]

    def test_the_read_point_does_not_move_while_the_loop_runs(self) -> None:
        """Every iteration of the turn marks the same block: the first writes it."""
        history = [_user("Q1"), _assistant(_text("A1")), _user("Q2")]
        first = shape_claude_payload(_loop(*history))
        later = shape_claude_payload(
            _loop(*history, _assistant(_tool_use("t1")), _tool_result("t1"))
        )
        assert first["messages"][1] == later["messages"][1]
        assert _marked(later["messages"][1])

    def test_a_first_turn_has_no_history_to_mark(self) -> None:
        payload = shape_claude_payload(_loop(_user("Hello")))
        assert not _marked(payload["messages"][0])

    def test_a_single_call_gets_no_read_point(self) -> None:
        """No rolling breakpoint writes its span: marking the history would pay
        the write premium on every turn for a prefix only frequent turns read."""
        payload = shape_claude_payload(
            {
                "system": f"{STATIC}\n{DYNAMIC}",
                "messages": [_user("Q1"), _assistant(_text("A1")), _user("Q2")],
            }
        )
        assert not _marked(payload["messages"][1])

    def test_breakpoints_a_caller_placed_in_the_messages_are_left_alone(self) -> None:
        payload = shape_claude_payload(
            _loop(
                _user("Q1"),
                _assistant(_text("A1")),
                {"role": "user", "content": [_text("Q2", cache_control=CC)]},
            )
        )
        assert not _marked(payload["messages"][1])

    def test_the_read_point_never_crowds_out_the_rolling_breakpoint(self) -> None:
        """Three explicit breakpoints leave one slot: the rolling one keeps it."""
        payload = shape_claude_payload(
            {
                "system": [_text(f"block {i}", cache_control=CC) for i in range(3)],
                "messages": [_user("Q1"), _assistant(_text("A1")), _user("Q2")],
                "tools": [{"name": "a"}, {"name": "b"}],
            }
        )
        assert not _marked(payload["messages"][1])
        assert payload["cache_control"] == CC

    def test_a_reasoning_block_is_never_the_one_marked(self) -> None:
        """A thinking block cannot carry ``cache_control``: the text before it can."""
        kept = [{"type": "thinking", "thinking": "", "signature": "s"}, _text("A1")]
        messages = [_user("Q1"), {"role": "assistant", "content": kept}, _user("Q2")]
        payload = shape_claude_payload(_loop(*messages))
        content = payload["messages"][1]["content"]
        assert content[-1] == _text("A1", cache_control=CC)

    def test_no_cacheable_block_means_no_read_point(self) -> None:
        empty = {"role": "assistant", "content": [_text("")]}
        payload = shape_claude_payload(_loop(_user("Q1"), empty, _user("Q2")))
        assert not _marked(payload["messages"][1])

    def test_the_payload_given_is_never_mutated_beyond_its_messages_list(self) -> None:
        answer = _assistant(_text("A1"))
        shape_claude_payload(_loop(_user("Q1"), answer, _user("Q2")))
        assert answer == _assistant(_text("A1"))


HOUR = {"type": "ephemeral", "ttl": "1h"}


def _breakpoints_in_render_order(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Every ``cache_control`` in the order the API renders the prompt."""
    found: list[dict[str, Any]] = []
    for block in payload.get("tools") or []:
        if "cache_control" in block:
            found.append(block["cache_control"])
    system = payload.get("system")
    for block in system if isinstance(system, list) else []:
        if "cache_control" in block:
            found.append(block["cache_control"])
    for message in payload.get("messages") or []:
        for block in message["content"] if isinstance(message["content"], list) else []:
            if isinstance(block, dict) and "cache_control" in block:
                found.append(block["cache_control"])
    if "cache_control" in payload:  # the automatic breakpoint lands on the last block
        found.append(payload["cache_control"])
    return found


class TestTheLifetimeFollowsTheRole:
    """The cross-turn read points live the hour when asked; the loop's tail never does (ADR-362)."""

    def test_an_extended_turn_marks_its_two_read_points_for_the_hour(self) -> None:
        payload = shape_claude_payload(
            _loop(_user("Q1"), _assistant(_text("A1")), _user("Q2")), extended_ttl=True
        )
        assert payload["system"][0]["cache_control"] == HOUR
        assert _marked(payload["messages"][1]) == [_text("A1", cache_control=HOUR)]

    def test_the_rolling_breakpoint_keeps_five_minutes(self) -> None:
        """It is re-read seconds later by the next iteration: an hour would bill
        every iteration's delta at 2x for nothing."""
        payload = shape_claude_payload(
            _loop(_user("Q1"), _assistant(_text("A1")), _user("Q2")), extended_ttl=True
        )
        assert payload["cache_control"] == CC

    def test_the_hour_always_comes_before_five_minutes(self) -> None:
        """The API refuses a one-hour entry after a five-minute one."""
        for messages in (
            [_user("Q1")],
            [_user("Q1"), _assistant(_text("A1")), _user("Q2")],
            [
                _user("Q1"),
                _assistant(_text("A1")),
                _user("Q2"),
                _assistant(_tool_use("t")),
                _tool_result("t"),
            ],
        ):
            order = _breakpoints_in_render_order(
                shape_claude_payload(_loop(*messages), extended_ttl=True)
            )
            lifetimes = ["1h" if marker.get("ttl") == "1h" else "5m" for marker in order]
            assert lifetimes == sorted(lifetimes, key=lambda lifetime: lifetime != "1h"), lifetimes

    def test_a_single_call_asked_for_the_hour_marks_its_static_prefix_only(self) -> None:
        payload = shape_claude_payload(
            {"system": f"{STATIC}\n{DYNAMIC}", "messages": [_user("Hi")]}, extended_ttl=True
        )
        assert payload["system"][0]["cache_control"] == HOUR
        assert "cache_control" not in payload

    def test_nothing_asked_keeps_every_breakpoint_at_five_minutes(self) -> None:
        payload = shape_claude_payload(_loop(_user("Q1"), _assistant(_text("A1")), _user("Q2")))
        assert all(marker == CC for marker in _breakpoints_in_render_order(payload))

    def test_breakpoints_a_caller_placed_keep_their_own_lifetime(self) -> None:
        system = [_text(f"{STATIC}\n{DYNAMIC}", cache_control=CC)]
        payload = shape_claude_payload(
            {"system": system, "messages": [_user("Hi")]}, extended_ttl=True
        )
        assert payload["system"][0]["cache_control"] == CC

    def test_beside_a_callers_breakpoint_nothing_added_lives_the_hour(self) -> None:
        """The tools render first: an hour placed after a caller's five minutes
        there is a 400 on every call, so the policy keeps the default."""
        payload = _loop(_user("Q1"), _assistant(_text("A1")), _user("Q2"))
        payload["tools"][0]["cache_control"] = CC
        shaped = shape_claude_payload(payload, extended_ttl=True)
        assert all(marker == CC for marker in _breakpoints_in_render_order(shaped))


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
        """Unless the call asked for the extended horizon, every breakpoint is the
        provider's default lifetime (``TestTheLifetimeFollowsTheRole`` covers the
        hour, which only the turn's doors price -- ADR-362)."""
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
