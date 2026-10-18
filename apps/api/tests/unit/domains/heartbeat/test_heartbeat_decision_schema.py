"""Tests for the extended HeartbeatDecision schema (ADR-135)."""

from collections.abc import Sequence

import pytest
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable
from pydantic import ValidationError

from src.domains.heartbeat.schemas import HeartbeatDecision
from src.infrastructure.llm.structured_output import _structured_via_auto_tool


class _AnswersWithAToolCall(FakeMessagesListChatModel):
    """A chat model answering its scripted messages, whatever tools it is bound to."""

    def bind_tools(
        self,
        tools: Sequence[object],
        *,
        tool_choice: str | None = None,
        **kwargs: object,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        return self


@pytest.mark.unit
class TestExtendedDecision:
    def test_valid_enum_labels_accepted(self) -> None:
        decision = HeartbeatDecision(
            action="notify",
            reason="r",
            message_draft="m",
            sources_used=["USER_INTERESTS", "CURRENT_WEATHER"],
            interest_topic="Cinéma A24",
        )
        assert decision.interest_topic == "Cinéma A24"

    def test_a_respelled_label_is_repaired(self) -> None:
        decision = HeartbeatDecision(
            action="skip",
            reason="r",
            sources_used=["USER MEMORIES", "workboard", "upcoming-calendar-events"],
        )
        assert decision.sources_used == ["USER_MEMORIES", "WORKBOARD", "UPCOMING_CALENDAR_EVENTS"]

    def test_a_label_naming_no_source_is_dropped_never_fatal(self) -> None:
        """Production 2026-10-17: one such label cost the WHOLE decision, three ticks of five."""
        decision = HeartbeatDecision(
            action="notify",
            reason="r",
            message_draft="m",
            sources_used=["UNREAD_EMAILS", "USER_RHYTHM", "RECENT_HEARTBEAT_NOTIFICATIONS", 3],
        )
        assert decision.sources_used == ["UNREAD_EMAILS"]

    def test_a_single_label_and_null_are_read_as_lists(self) -> None:
        single = HeartbeatDecision(action="skip", reason="r", sources_used="HABITS")
        null = HeartbeatDecision(action="skip", reason="r", sources_used=None)

        assert single.sources_used == ["HABITS"]
        assert null.sources_used == []

    def test_a_wrong_type_stays_an_error(self) -> None:
        with pytest.raises(ValidationError):
            HeartbeatDecision(action="skip", reason="r", sources_used={"a": 1})

    def test_the_published_schema_still_names_the_vocabulary(self) -> None:
        """The enum is what steers the model: tolerance must not cost it."""
        items = HeartbeatDecision.model_json_schema()["properties"]["sources_used"]["items"]

        assert "UNREAD_EMAILS" in items["enum"]
        assert "USER_RHYTHM" not in items["enum"]

    async def test_the_auto_tool_door_keeps_the_decision(self) -> None:
        """The incident, replayed on the door a model that refuses a forced tool takes."""
        raw = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "HeartbeatDecision",
                    "args": {
                        "action": "skip",
                        "reason": "Quiet hours.",
                        "sources_used": ["UPCOMING_CALENDAR_EVENTS", "OPEN_LOOPS", "USER_RHYTHM"],
                    },
                    "id": "call_1",
                    "type": "tool_call",
                }
            ],
        )

        decision = await _structured_via_auto_tool(
            llm=_AnswersWithAToolCall(responses=[raw]),
            messages=[],
            schema=HeartbeatDecision,
            reasoning_emit=None,
            provider="anthropic",
        )

        assert decision is not None
        assert decision.sources_used == ["UPCOMING_CALENDAR_EVENTS", "OPEN_LOOPS"]

    def test_interest_topic_defaults_none(self) -> None:
        decision = HeartbeatDecision(action="skip", reason="r")
        assert decision.interest_topic is None


@pytest.mark.unit
class TestLegacyRowsStillSerialize:
    """The canonical Literal is confined to the LLM structured output.

    Production rows predating ADR-135 carry free-text labels ("USER MEMORIES");
    the history API must keep serializing them, so the response schema stays
    `list[str]`. This test pins that blast radius.
    """

    def test_history_response_accepts_legacy_labels(self) -> None:
        from datetime import UTC, datetime
        from uuid import uuid4

        from src.domains.heartbeat.schemas import HeartbeatNotificationResponse

        response = HeartbeatNotificationResponse(
            id=uuid4(),
            created_at=datetime.now(UTC),
            content="legacy notification",
            sources_used=["USER MEMORIES", "calendar"],  # both legacy spellings
            priority="low",
            user_feedback=None,
        )

        assert response.sources_used == ["USER MEMORIES", "calendar"]
