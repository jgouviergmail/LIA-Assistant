"""The person's own words are quoted under the summary, within a budget (lot 16).

Measured 2026-11-15 on the recall bench (``task agents:compaction:measure``): the
compaction slot configured on dev kept all 17 of the person's planted words, but a small
summarizer of another family kept 12 (four constraints buried in a dense discussion
vanished in the multi-chunk merge), and the truncation fallback, which writes no summary,
kept none. What the person wrote is therefore quoted as written, under the summary and
in the truncation notice: the most recent first within ``COMPACTION_PERSON_WORDS_MAX_TOKENS``,
the rest counted. Only the person's words are quoted (a message stamped with when it was
written, ADR-381); a scaffold the node writes as a human message is not theirs. The
quotes travel on the summary message, so a later compaction carries them without asking
a model to merge them again.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from src.core.config import settings
from src.core.constants import COMPACTION_PERSON_WORDS_KEY, COMPACTION_SUMMARY_MARKER
from src.domains.agents.nodes.compaction_node import compaction_node
from src.domains.agents.services.compaction_service import (
    CompactionResult,
    CompactionService,
    SafetyCheckResult,
)
from src.infrastructure.llm.message_view import stamped_now

pytestmark = pytest.mark.unit

_AT = datetime(2026, 11, 2, 8, 30, tzinfo=UTC)


def _said(text: str, minutes: int) -> HumanMessage:
    return stamped_now(HumanMessage(text, id=f"said-{minutes}"), _AT + timedelta(minutes=minutes))


def _history() -> list[BaseMessage]:
    return [
        _said("Never book a flight before 10am.", 0),
        AIMessage("Noted.", id="a0"),
        # A scaffold the node writes as a human message: not the person's words.
        HumanMessage("Conversation history has been compacted. Please confirm.", id="scaffold"),
        AIMessage("Done.", id="a1"),
        _said("My daughter Inès is coming with us.", 10),
        AIMessage("Lovely.", id="a2"),
        _said("Which museum then?", 20),
        AIMessage("The Confluences.", id="a3"),
    ]


def _summarizer(*answers: str) -> FakeListChatModel:
    return FakeListChatModel(responses=list(answers))


async def _compact(messages: list[BaseMessage], *answers: str) -> CompactionResult:
    with patch(
        "src.domains.agents.services.compaction_service.get_llm",
        return_value=_summarizer(*answers),
    ):
        return await CompactionService().compact(
            messages, preserve_recent_n=2, language="en", zone=UTC
        )


class TestTheQuotes:
    async def test_what_the_person_wrote_is_quoted_whatever_the_summary_kept(self) -> None:
        result = await _compact(_history(), "## Summary\n- Travel planning.")

        assert result.summary.startswith("## Summary\n- Travel planning.")
        assert "Never book a flight before 10am." in result.summary
        assert "My daughter Inès is coming with us." in result.summary
        assert "Please confirm" not in result.summary.split("Travel planning.", 1)[1]
        assert [quote["text"] for quote in result.person_words] == [
            "Never book a flight before 10am.",
            "My daughter Inès is coming with us.",
        ]
        assert result.summary.index("10am") < result.summary.index("Inès"), "oldest first"

    async def test_the_newest_fit_the_budget_and_the_rest_is_counted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        one_quote = CompactionService()._token_counter.count_tokens(
            "- [Mon 02 Nov 2026, 08:40] My daughter Inès is coming with us."
        )
        monkeypatch.setattr(settings, "compaction_person_words_max_tokens", one_quote + 2)

        result = await _compact(_history(), "## Summary\n- Travel planning.")

        assert [quote["text"] for quote in result.person_words] == [
            "My daughter Inès is coming with us."
        ]
        assert "10am" not in result.summary
        assert "1 earlier" in result.summary, "the cut is stated with its count"

    async def test_a_budget_of_zero_quotes_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "compaction_person_words_max_tokens", 0)

        result = await _compact(_history(), "## Summary\n- Travel planning.")

        assert result.person_words == []
        assert "Inès" not in result.summary

    async def test_a_later_compaction_carries_the_earlier_quotes_as_written(self) -> None:
        earlier = SystemMessage(
            f"{COMPACTION_SUMMARY_MARKER} — compaction #1.]\n\nOlder summary.",
            id="summary-1",
            additional_kwargs={
                COMPACTION_PERSON_WORDS_KEY: [
                    {
                        "written_at": (_AT - timedelta(days=1)).isoformat(),
                        "text": "Strawberries make me ill.",
                    }
                ]
            },
        )

        result = await _compact(
            [earlier, *_history()], "Chunk summary.", "## Summary\n- Merged, words lost."
        )

        assert result.consolidated_previous_summaries
        assert [quote["text"] for quote in result.person_words] == [
            "Strawberries make me ill.",
            "Never book a flight before 10am.",
            "My daughter Inès is coming with us.",
        ]
        assert "Strawberries make me ill." in result.summary

    def test_the_truncation_notice_quotes_the_person_too(self) -> None:
        fallback = CompactionService()._truncation_fallback(
            _history(), 2, reason="timeout", zone=UTC
        )

        assert "Never book a flight before 10am." in fallback.summary
        assert "My daughter Inès is coming with us." in fallback.summary
        assert len(fallback.person_words) == 2


class TestTheSummaryMessage:
    async def test_the_quotes_ride_on_the_summary_message(self) -> None:
        quotes = [{"written_at": _AT.isoformat(), "text": "Never book a flight before 10am."}]
        service = MagicMock()
        service.should_compact.return_value = True
        service.is_safe_to_compact.return_value = SafetyCheckResult(safe=True)
        service.compact = AsyncMock(
            return_value=CompactionResult(
                summary="Recap.",
                tokens_before=900,
                tokens_after=50,
                tokens_saved=850,
                identifiers_preserved=[],
                strategy="single_chunk",
                person_words=quotes,
            )
        )
        with (
            patch(
                "src.domains.agents.nodes.compaction_node.CompactionService", return_value=service
            ),
            patch(
                "src.domains.agents.nodes.compaction_node.get_stream_writer",
                return_value=MagicMock(),
            ),
        ):
            result = await compaction_node(
                {"messages": _history(), "user_language": "en", "compaction_count": 0},
                config={},
            )

        summary = next(m for m in result["messages"] if isinstance(m, SystemMessage))
        assert summary.additional_kwargs[COMPACTION_PERSON_WORDS_KEY] == quotes
