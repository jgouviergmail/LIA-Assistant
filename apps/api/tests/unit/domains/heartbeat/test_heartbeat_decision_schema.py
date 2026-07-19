"""Tests for the extended HeartbeatDecision schema (ADR-135)."""

import pytest
from pydantic import ValidationError

from src.domains.heartbeat.schemas import HeartbeatDecision


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

    def test_free_text_label_rejected(self) -> None:
        with pytest.raises(ValidationError):
            HeartbeatDecision(
                action="notify",
                reason="r",
                message_draft="m",
                sources_used=["USER MEMORIES"],  # space variant seen in prod
            )

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
