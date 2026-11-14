"""The query analyzer reads each turn with when the person wrote it (lot 17)."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.core.constants import QUERY_ANALYZER_HISTORY_TURN_MAX_CHARS
from src.domains.agents.services.analysis.query_context import (
    extract_conversation_history,
    render_conversation_history,
)
from src.infrastructure.llm.message_view import stamped_now

pytestmark = pytest.mark.unit

TOKYO = ZoneInfo("Asia/Tokyo")
TUESDAY = datetime(2026, 11, 10, 0, 12, tzinfo=UTC)
FRIDAY = datetime(2026, 11, 13, 9, 30, tzinfo=UTC)


def test_each_message_the_person_wrote_reads_with_its_instant() -> None:
    messages = [
        stamped_now(HumanMessage("I have the dentist tomorrow at 10."), TUESDAY),
        AIMessage("Noted."),
        stamped_now(HumanMessage("Is it still ahead of me?"), FRIDAY),
    ]

    history = extract_conversation_history(messages, zone=TOKYO)

    assert history == [
        {"role": "user", "content": "[Tue 10 Nov 2026, 09:12] I have the dentist tomorrow at 10."},
        {"role": "assistant", "content": "Noted."},
        {"role": "user", "content": "[Fri 13 Nov 2026, 18:30] Is it still ahead of me?"},
    ]


def test_the_stamp_never_takes_the_room_of_what_the_person_wrote() -> None:
    """Each turn keeps its whole text budget; the moment is added before it."""
    long_text = "x" * (QUERY_ANALYZER_HISTORY_TURN_MAX_CHARS + 50)
    messages = [stamped_now(HumanMessage(long_text), TUESDAY), AIMessage(long_text)]

    stamped, plain = extract_conversation_history(messages, zone=TOKYO)

    kept = "x" * QUERY_ANALYZER_HISTORY_TURN_MAX_CHARS
    assert stamped["content"] == f"[Tue 10 Nov 2026, 09:12] {kept}"
    assert plain["content"] == kept


def test_the_prompt_shows_each_turn_as_projected_with_no_second_cut() -> None:
    long_text = "x" * (QUERY_ANALYZER_HISTORY_TURN_MAX_CHARS + 50)
    history = extract_conversation_history(
        [stamped_now(HumanMessage(long_text), TUESDAY)], zone=TOKYO
    )

    rendered = render_conversation_history(history, window_size=5)

    assert rendered == f"[user]: {history[0]['content']}"


def test_the_prompt_keeps_the_last_window_and_says_none_for_an_empty_history() -> None:
    history = [{"role": "user", "content": f"q{index}"} for index in range(8)]

    assert render_conversation_history(history, window_size=2) == "[user]: q6\n[user]: q7"
    assert render_conversation_history([], window_size=5) == "None"


def test_the_window_counts_turns_as_before() -> None:
    messages = [HumanMessage(f"q{index}") for index in range(20)]

    history = extract_conversation_history(messages, zone=TOKYO, window_size=2)

    assert [item["content"] for item in history] == ["q16", "q17", "q18", "q19"]
