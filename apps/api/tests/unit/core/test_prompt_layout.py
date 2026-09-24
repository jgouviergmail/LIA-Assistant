"""Where a versioned prompt's static part ends, and what a single call sends (ADR-309).

Every versioned prompt keeps what each call repeats above one line holding
``DYNAMIC_CONTEXT_MARKER`` and the call's own data below it. Sent whole as ONE
user message, that static part was invisible to the payload shapers, which mark
instruction roles only: measured 2026-09-23 on gpt-6-luna, every extraction read
0 % of its prompt from the cache and wrote all of it at 1.25x. The static part
goes out as the system message, ending on the marker's line — where the shapers
cut and where the OpenAI cache key stops.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.core.prompt_layout import single_call_messages, split_at_marker

pytestmark = pytest.mark.unit

STATIC = "Extract the facts.\nRules every call repeats.\n"
MARKER_LINE = f"{DYNAMIC_CONTEXT_MARKER} (all variable data below) ---"
DYNAMIC = "Conversation:\nuser: I moved to Lyon."
PROMPT = f"{STATIC}\n{MARKER_LINE}\n\n{DYNAMIC}\n"


class TestTheSplit:
    def test_the_static_part_ends_on_the_markers_line(self) -> None:
        split = split_at_marker(PROMPT)

        assert split is not None
        assert split.static == f"{STATIC}\n{MARKER_LINE}"
        assert split.marker_line == MARKER_LINE
        assert split.dynamic == DYNAMIC

    def test_a_prompt_without_the_marker_has_no_split(self) -> None:
        assert split_at_marker("Just a question.") is None

    def test_a_marker_on_the_last_line(self) -> None:
        split = split_at_marker(f"{STATIC}{MARKER_LINE}")

        assert split is not None
        assert split.static == f"{STATIC}{MARKER_LINE}"
        assert split.dynamic == ""


class TestWhatASingleCallSends:
    def test_the_static_part_is_the_system_message_and_the_data_the_question(self) -> None:
        messages = single_call_messages(PROMPT)

        assert [type(message) for message in messages] == [SystemMessage, HumanMessage]
        assert messages[0].content == f"{STATIC}\n{MARKER_LINE}"
        assert messages[1].content == DYNAMIC

    def test_the_model_reads_the_same_text(self) -> None:
        messages = single_call_messages(PROMPT)

        joined = "\n\n".join(str(message.content) for message in messages)
        assert joined.split() == PROMPT.split()

    def test_a_prompt_without_the_marker_stays_one_user_message(self) -> None:
        assert single_call_messages("Just a question.") == [
            HumanMessage(content="Just a question.")
        ]

    def test_a_prompt_with_nothing_after_the_marker_stays_one_user_message(self) -> None:
        prompt = f"{STATIC}{MARKER_LINE}\n"

        assert single_call_messages(prompt) == [HumanMessage(content=prompt)]
