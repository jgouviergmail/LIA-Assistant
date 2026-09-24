"""With the cross-turn cache flag, the turn's context comes AFTER the question (ADR-308).

A ReAct call sends ``[tools][system][history][question][loop]``. The system
prompt ends with the turn's own data -- the date, the domains' type links, the
memories, the skills -- so everything a provider could cache after the static
prompt changed on every turn, and on DeepSeek, whose prefix puts the system
BEFORE the tools, even the tools were never read again (measured 2026-09-23:
binding every tool without moving the context cost 44 % more there). With the
flag, the leading system message is the static prompt alone, still ending on the
marker where every payload shaper cuts its breakpoint, and the turn's data
follows the question: tools and static prompt are byte-identical from one turn
to the next.

« After the question » has one shape per provider, DECLARED: Anthropic refuses a
system message that is not first (``langchain_anthropic`` raises), and
``langchain-google-genai`` merges one back into the system instruction, where the
data would never have moved. Those take the context appended to the question's
own message, as text; the three whose trailing system message was measured on
the real API keep the system role.
"""

from __future__ import annotations

from typing import Any, get_args

import pytest
from langchain_anthropic.chat_models import _format_messages
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_google_genai.chat_models import _parse_chat_history

from src.core.constants import COMPACTION_SUMMARY_MARKER, DYNAMIC_CONTEXT_MARKER
from src.domains.agents.models import count_messages_tokens_cached
from src.domains.agents.nodes import react_turn_layout as layout
from src.domains.agents.nodes.react_prompt import build_system_prompt
from src.domains.agents.nodes.react_turn_layout import (
    CONTEXT_PLACEMENT,
    ContextPlacement,
    assert_context_placement_completeness,
    compose_turn_messages,
)
from src.infrastructure.llm.providers.adapter import ProviderType
from src.infrastructure.llm.providers.anthropic_payload import shape_claude_payload
from src.infrastructure.llm.providers.openai_payload import mark_static_system_prefix
from src.infrastructure.llm.providers.responses_adapter import compute_prompt_cache_key

pytestmark = pytest.mark.unit

STATIC = "<Role>You are LIA.</Role>\n\n<Rules>Use the tools.</Rules>\n\n"
MARKER_LINE = f"{DYNAMIC_CONTEXT_MARKER} (all variable data below) ---"
MEMORY = "<UserMemories>Likes tea.</UserMemories>"
SKILLS = "<SkillsCatalog>trip-planner</SkillsCatalog>"
QUESTION = HumanMessage(content="What is on my calendar?", id="q")
LOOP: list[BaseMessage] = [
    AIMessage(
        content="", id="l1", tool_calls=[{"id": "c1", "name": "get_events_tool", "args": {}}]
    ),
    ToolMessage(content="3 events", tool_call_id="c1", name="get_events_tool", id="l2"),
]
TRAILING = ("openai", "deepseek", "qwen")


def _prompt(date: str) -> str:
    return f"{STATIC}{MARKER_LINE}\n\n<Context>\nDate: {date}\n</Context>"


def _blocks(date: str = "2026-09-23 18:00") -> list[str]:
    return [_prompt(date), MEMORY, SKILLS]


def _history(first: int, turns: int) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for turn in range(first, first + turns):
        messages += [
            HumanMessage(content=f"question {turn}", id=f"h{turn}"),
            AIMessage(content=f"answer {turn}", id=f"a{turn}"),
        ]
    return messages


def _windowed(*, loop: bool = True, question: HumanMessage = QUESTION) -> list[BaseMessage]:
    return [*_history(0, 2), question, *(LOOP if loop else [])]


def _compose(provider: str | None, **kwargs: Any) -> list[BaseMessage]:
    return compose_turn_messages(
        kwargs.get("blocks", _blocks()),
        kwargs.get("windowed", _windowed()),
        context_after_question=kwargs.get("flag", True),
        provider=provider,
    )


def _position(payload: list[BaseMessage], message_id: str) -> int:
    return next(i for i, message in enumerate(payload) if message.id == message_id)


def _text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(part["text"] for part in content if isinstance(part, dict) and "text" in part)


class TestFlagOff:
    @pytest.mark.parametrize("provider", [*get_args(ProviderType), None])
    def test_the_layout_is_today_s_whatever_the_provider(self, provider: str | None) -> None:
        payload = _compose(provider, flag=False)
        assert payload == [SystemMessage(content=block) for block in _blocks()] + _windowed()


class TestPlacementTable:
    def test_every_provider_declares_where_its_context_goes(self) -> None:
        assert set(CONTEXT_PLACEMENT) == set(get_args(ProviderType))
        assert_context_placement_completeness()

    def test_a_provider_without_a_declaration_refuses_to_boot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delitem(layout.CONTEXT_PLACEMENT, "qwen")
        with pytest.raises(AssertionError, match="qwen"):
            assert_context_placement_completeness()

    def test_the_measured_providers_keep_the_system_role(self) -> None:
        placements = {provider: CONTEXT_PLACEMENT[provider] for provider in get_args(ProviderType)}
        assert {p for p, v in placements.items() if v is ContextPlacement.TRAILING_SYSTEM} == set(
            TRAILING
        )


class TestTrailingSystem:
    @pytest.mark.parametrize("provider", TRAILING)
    def test_the_leading_system_is_the_static_prompt_ending_on_the_marker(
        self, provider: str
    ) -> None:
        payload = _compose(provider)
        assert payload[0] == SystemMessage(content=f"{STATIC}{MARKER_LINE}")
        before_question = payload[: _position(payload, "q")]
        assert [m for m in before_question if isinstance(m, SystemMessage)] == [payload[0]]

    @pytest.mark.parametrize("provider", TRAILING)
    def test_the_turn_s_context_follows_the_question(self, provider: str) -> None:
        payload = _compose(provider)
        context = payload[_position(payload, "q") + 1]
        assert isinstance(context, SystemMessage)
        text = _text(context)
        assert text.startswith(MARKER_LINE)
        assert text.index("Date: 2026-09-23 18:00") < text.index(MEMORY) < text.index(SKILLS)

    def test_the_loop_follows_the_context_and_nothing_else_moves(self) -> None:
        windowed = _windowed()
        payload = _compose("deepseek", windowed=windowed)
        question_at = _position(payload, "q")
        assert payload[1:question_at] == windowed[: windowed.index(QUESTION)]
        assert payload[question_at] is QUESTION
        assert payload[question_at + 2 :] == LOOP

    def test_nothing_it_was_given_is_mutated(self) -> None:
        blocks, windowed = _blocks(), _windowed()
        frozen_blocks, frozen_windowed = list(blocks), list(windowed)
        _compose("openai", blocks=blocks, windowed=windowed)
        assert blocks == frozen_blocks and windowed == frozen_windowed
        assert QUESTION.content == "What is on my calendar?"


class TestQuestionTail:
    def test_the_context_closes_the_question_s_own_message(self) -> None:
        payload = _compose("anthropic")
        question = payload[_position(payload, "q")]
        assert isinstance(question, HumanMessage) and isinstance(question.content, str)
        assert question.content.startswith(f"What is on my calendar?\n\n{MARKER_LINE}")
        text = question.content
        assert text.index("Date: 2026-09-23 18:00") < text.index(MEMORY) < text.index(SKILLS)
        assert payload[_position(payload, "q") + 1 :] == LOOP

    def test_the_delivered_context_metric_still_counts_it(self) -> None:
        """The token counter the loop observes counts text content only: the moved
        context must stay text, or the metric would lose the turn's whole context."""
        closed = _compose("anthropic")[_position(_compose("anthropic"), "q")]
        assert count_messages_tokens_cached([closed]) > count_messages_tokens_cached(
            [QUESTION]
        ) + count_messages_tokens_cached([HumanMessage(content=MEMORY)])

    def test_a_question_that_carries_parts_keeps_them(self) -> None:
        image = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}
        asked = HumanMessage(content=[{"type": "text", "text": "What is this?"}, image], id="q")
        payload = _compose("gemini", windowed=_windowed(question=asked))
        content = payload[_position(payload, "q")].content
        assert content[:2] == [{"type": "text", "text": "What is this?"}, image]
        assert content[2]["text"].startswith(MARKER_LINE)

    def test_an_empty_question_is_the_context_alone(self) -> None:
        """No blank lines before the context when the question itself is empty."""
        payload = _compose(
            "anthropic", windowed=_windowed(question=HumanMessage(content="", id="q"))
        )
        assert payload[_position(payload, "q")].content.startswith(MARKER_LINE)

    def test_anthropic_formats_it_with_the_static_prompt_alone_in_the_system(self) -> None:
        system, formatted = _format_messages(_compose("anthropic"))
        system_text = system if isinstance(system, str) else "".join(b["text"] for b in system)
        assert "Date:" not in system_text and system_text.rstrip().endswith(MARKER_LINE)
        assert "Date: 2026-09-23 18:00" in str(formatted)

    def test_a_system_message_after_the_question_is_what_anthropic_refuses(self) -> None:
        with pytest.raises(ValueError):
            _format_messages(_compose("deepseek"))

    def test_gemini_keeps_the_context_after_the_question(self) -> None:
        system, contents = _parse_chat_history(_compose("gemini"))
        assert system is not None
        assert "Date:" not in "".join(part.text or "" for part in system.parts or [])
        question = next(c for c in contents if "What is on my calendar?" in str(c))
        assert "Date: 2026-09-23 18:00" in str(question)

    def test_gemini_would_fold_a_trailing_system_message_back_into_the_system(self) -> None:
        system, _ = _parse_chat_history(_compose("deepseek"))
        assert system is not None
        assert "Date: 2026-09-23 18:00" in "".join(part.text or "" for part in system.parts or [])

    def test_an_undeclared_provider_gets_the_shape_every_client_accepts(self) -> None:
        payload = _compose("not-a-provider")
        assert [m for m in payload if isinstance(m, SystemMessage)] == [payload[0]]
        assert _text(payload[_position(payload, "q")]).endswith(SKILLS)


class TestPrefixStability:
    def _turn(self, date: str, first: int, provider: str, *, flag: bool) -> list[BaseMessage]:
        question = HumanMessage(content=f"question {first + 2}", id="q")
        return compose_turn_messages(
            _blocks(date),
            [*_history(first, 2), question],
            context_after_question=flag,
            provider=provider,
        )

    @pytest.mark.parametrize("provider", [*TRAILING, "anthropic", "gemini"])
    def test_the_leading_system_is_the_same_on_the_next_turn(self, provider: str) -> None:
        now = self._turn("2026-09-23 18:00", 0, provider, flag=True)
        later = self._turn("2026-09-23 18:04", 1, provider, flag=True)
        assert now[0] == later[0]
        before = self._turn("2026-09-23 18:00", 0, provider, flag=False)
        after = self._turn("2026-09-23 18:04", 1, provider, flag=False)
        assert before[0] != after[0], "today the turn's data sits inside the leading system"

    def test_openai_keeps_one_prompt_cache_key(self) -> None:
        now = self._turn("2026-09-23 18:00", 0, "openai", flag=True)
        later = self._turn("2026-09-23 18:04", 1, "openai", flag=True)
        assert compute_prompt_cache_key(now, "gpt-6-luna") == compute_prompt_cache_key(
            later, "gpt-6-luna"
        )

    def test_the_openai_shaper_marks_the_static_prompt_and_nothing_after_it(self) -> None:
        payload = _compose("openai")
        items = [
            {"role": "system" if isinstance(m, SystemMessage) else "user", "content": _text(m)}
            for m in payload
            if isinstance(m, (SystemMessage, HumanMessage))
        ]
        marked = mark_static_system_prefix(items)
        breakpoints = [
            (index, block["text"])
            for index, item in enumerate(marked)
            if isinstance(item["content"], list)
            for block in item["content"]
            if "prompt_cache_breakpoint" in block
        ]
        assert breakpoints == [(0, STATIC)]

    def test_the_claude_shaper_marks_the_static_prompt(self) -> None:
        system, messages = _format_messages(_compose("anthropic"))
        tools = [{"name": "a", "input_schema": {}}, {"name": "b", "input_schema": {}}]
        shaped = shape_claude_payload({"system": system, "messages": messages, "tools": tools})
        marked = [block for block in shaped["system"] if "cache_control" in block]
        assert [block["text"] for block in marked] == [STATIC.rstrip()]


class TestEdges:
    def test_no_block_leaves_the_history_as_it_is(self) -> None:
        assert _compose("deepseek", blocks=[]) == _windowed()

    def test_no_question_leaves_the_layout_as_it_is(self) -> None:
        windowed = [m for m in _windowed() if not isinstance(m, HumanMessage)]
        payload = _compose("deepseek", windowed=windowed)
        assert payload == [SystemMessage(content=block) for block in _blocks()] + windowed

    def test_nothing_dynamic_leaves_the_layout_as_it_is(self) -> None:
        payload = _compose("deepseek", blocks=[f"{STATIC}{MARKER_LINE}"])
        assert payload == [SystemMessage(content=f"{STATIC}{MARKER_LINE}"), *_windowed()]

    def test_a_prompt_without_the_marker_stays_whole_and_the_blocks_move(self) -> None:
        payload = _compose("deepseek", blocks=["STATIC ONLY", MEMORY])
        assert payload[0] == SystemMessage(content="STATIC ONLY")
        assert _text(payload[_position(payload, "q") + 1]) == f"{DYNAMIC_CONTEXT_MARKER}\n{MEMORY}"

    def test_the_compaction_summary_stays_with_the_leading_system(self) -> None:
        summary = SystemMessage(content=f"{COMPACTION_SUMMARY_MARKER} The user plans a trip.")
        payload = _compose("anthropic", windowed=[summary, *_windowed()])
        assert payload[1] is summary
        system, _ = _format_messages(payload)
        assert system is not None


def test_the_real_react_prompt_splits_on_its_marker() -> None:
    """The template itself: its static part leads, its date follows the question."""
    prompt = build_system_prompt({"messages": [], "user_language": "fr"})
    payload = compose_turn_messages(
        [prompt], _windowed(loop=False), context_after_question=True, provider="deepseek"
    )
    assert "Date:" not in _text(payload[0])
    assert _text(payload[0]).rstrip().endswith("---")
    assert "Date:" in _text(payload[-1])
