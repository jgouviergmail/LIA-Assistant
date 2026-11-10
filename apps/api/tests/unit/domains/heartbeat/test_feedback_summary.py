"""What proactive notifications met, offered to the habits domain (ADR-375)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domains.habits import usage_ports
from src.domains.habits.proposal_rules import ProactiveFeedback
from src.domains.heartbeat import feedback_summary

pytestmark = pytest.mark.unit


async def test_sent_and_reacted_are_counted_since_the_window_start() -> None:
    result = MagicMock()
    result.one.return_value = (41, 3)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    feedback = await feedback_summary.read_proactive_feedback(
        db, uuid4(), datetime(2026, 10, 4, tzinfo=UTC)
    )
    assert feedback == ProactiveFeedback(sent=41, reacted=3)
    db.execute.assert_awaited_once()


def test_the_reader_is_offered_to_habits() -> None:
    usage_ports.install_proactive_feedback_reader(feedback_summary.read_proactive_feedback)
    assert usage_ports.proactive_feedback_reader() is feedback_summary.read_proactive_feedback
