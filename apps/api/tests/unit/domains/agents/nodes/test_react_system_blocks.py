"""The ReAct turn's system blocks are state, and they lead the payload.

They used to be appended to ``state["messages"]``. Three consequences, all
measured before the change:

- **cost** — the windowing hoists every SystemMessage to the front, so a thread
  carried one full copy of the ReAct prompt (840 tokens) per past turn, resent
  on every LLM call of every iteration: 2 520 tokens after 3 turns, 8 400 after
  10;
- **prompt cache** — that growing prefix changed on every turn, so no provider
  prefix cache could ever hit;
- **Anthropic** — hoisted-old plus appended-new are NON-CONSECUTIVE system
  messages. ``langchain_anthropic._format_messages`` raises
  ``ValueError: Received multiple non-consecutive system messages.`` outright,
  from the second ReAct turn of a conversation onward.

The compaction summary is the one SystemMessage the history genuinely needs — it
IS the conversation's compressed memory — so the legacy filter must keep it. An
earlier version of this fix dropped every history SystemMessage in bulk and
silently destroyed it; that regression is pinned below.
"""

from __future__ import annotations

import pytest
from langchain_anthropic.chat_models import _format_messages
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.core.constants import COMPACTION_SUMMARY_MARKER
from src.domains.agents.nodes.react_history import (
    window_messages_for_react as _window_messages_for_react,
)

pytestmark = [pytest.mark.unit]

REACT_PROMPT = "REACT AGENT PROMPT " + ("x" * 3000)
COMPACTION = f"{COMPACTION_SUMMARY_MARKER} — compaction #1.]\n\nThe user plans a trip to Lisbon."


def _legacy_state(turns: int) -> list:
    """State written BEFORE the change: system blocks live in `messages`."""
    messages: list = []
    for turn in range(turns):
        messages.append(HumanMessage(f"question {turn}"))
        messages.append(SystemMessage(f"{REACT_PROMPT} (turn {turn})"))
        messages.append(SystemMessage(f"USER MODEL BLOCK (turn {turn})"))
        messages.append(AIMessage("", tool_calls=[{"id": f"c{turn}", "name": "tool", "args": {}}]))
        messages.append(ToolMessage("result", tool_call_id=f"c{turn}", name="tool"))
        messages.append(AIMessage(f"answer {turn}"))
    messages.append(HumanMessage("question courante"))
    return messages


def _current_state(turns: int, *, with_compaction: bool = False) -> list:
    """State written AFTER the change: no system block in `messages`."""
    messages: list = []
    if with_compaction:
        messages.append(SystemMessage(COMPACTION))
    for turn in range(turns):
        messages.append(HumanMessage(f"question {turn}"))
        messages.append(AIMessage("", tool_calls=[{"id": f"c{turn}", "name": "tool", "args": {}}]))
        messages.append(ToolMessage("result", tool_call_id=f"c{turn}", name="tool"))
        messages.append(AIMessage(f"answer {turn}"))
    messages.append(HumanMessage("question courante"))
    return messages


def _call_model_payload(state_messages: list, blocks: list[str]) -> list:
    """Reproduces what react_call_model_node hands to the provider."""
    windowed = _window_messages_for_react(state_messages)
    return [SystemMessage(content=block) for block in blocks] + windowed


class TestLegacyCheckpointHygiene:
    """Threads written before the change must not keep paying for it."""

    @pytest.mark.parametrize("turns", [1, 3, 5])
    def test_stale_react_blocks_are_dropped_from_history(self, turns: int) -> None:
        windowed = _window_messages_for_react(_legacy_state(turns))
        assert not [m for m in windowed if isinstance(m, SystemMessage)]

    def test_compaction_summary_survives(self) -> None:
        """The regression a bulk `include_system=False` would have introduced."""
        messages = [SystemMessage(COMPACTION), *_legacy_state(2)]
        windowed = _window_messages_for_react(messages)
        kept = [m for m in windowed if isinstance(m, SystemMessage)]
        assert len(kept) == 1
        assert str(kept[0].content).startswith(COMPACTION_SUMMARY_MARKER)

    def test_conversational_history_is_preserved(self) -> None:
        """Dropping system blocks must not drop the conversation with them."""
        windowed = _window_messages_for_react(_legacy_state(2))
        texts = [str(m.content) for m in windowed]
        assert "question 0" in texts
        assert "answer 1" in texts


class TestPayloadShape:
    def test_system_blocks_lead_and_are_contiguous(self) -> None:
        payload = _call_model_payload(
            _current_state(3), [REACT_PROMPT, "USER MODEL BLOCK", "<AvailableSkills>…"]
        )
        positions = [i for i, m in enumerate(payload) if isinstance(m, SystemMessage)]
        assert positions == [0, 1, 2]

    def test_compaction_summary_joins_the_leading_block(self) -> None:
        """It sits at the head of the windowed history, right after the blocks."""
        payload = _call_model_payload(_current_state(2, with_compaction=True), [REACT_PROMPT])
        positions = [i for i, m in enumerate(payload) if isinstance(m, SystemMessage)]
        assert positions == list(range(len(positions))), "system block is not contiguous"

    def test_no_blocks_yields_an_unchanged_payload(self) -> None:
        """Defensive: a resumed checkpoint may carry no blocks."""
        state = _current_state(2)
        assert _call_model_payload(state, []) == _window_messages_for_react(state)


class TestProviderCompatibility:
    """The failure that made this more than a cost problem."""

    @pytest.mark.parametrize("turns", [1, 2, 5])
    def test_anthropic_accepts_the_payload(self, turns: int) -> None:
        payload = _call_model_payload(_current_state(turns), [REACT_PROMPT, "USER MODEL"])
        system, formatted = _format_messages(payload)
        assert system is not None
        assert formatted

    def test_anthropic_accepts_a_payload_with_compaction(self) -> None:
        payload = _call_model_payload(_current_state(3, with_compaction=True), [REACT_PROMPT])
        system, _ = _format_messages(payload)
        assert system is not None

    def test_legacy_state_no_longer_raises(self) -> None:
        """The exact shape that used to break: old blocks + new leading blocks."""
        payload = _call_model_payload(_legacy_state(2), [REACT_PROMPT, "USER MODEL"])
        system, _ = _format_messages(payload)
        assert system is not None


class TestPrefixStability:
    """A prefix that changes every turn can never be cached by any provider."""

    def test_leading_system_bytes_are_identical_across_turns(self) -> None:
        blocks = [REACT_PROMPT, "USER MODEL BLOCK"]
        prefixes = []
        for turns in (1, 3, 5):
            payload = _call_model_payload(_current_state(turns), blocks)
            leading = [m for m in payload if isinstance(m, SystemMessage)]
            prefixes.append("".join(str(m.content) for m in leading))
        assert prefixes[0] == prefixes[1] == prefixes[2]

    def test_the_prompt_is_carried_exactly_once(self) -> None:
        """The measured defect: N copies of an 840-token prompt after N turns."""
        payload = _call_model_payload(_current_state(5), [REACT_PROMPT])
        rendered = "".join(str(m.content) for m in payload)
        assert rendered.count("REACT AGENT PROMPT") == 1
