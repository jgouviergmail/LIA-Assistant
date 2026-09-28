"""The conversation under way: the listener's last question, only when recent, only theirs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from src.domains.radio.facts import FactKind, Sensitivity
from src.domains.radio.readers.conversation import conversation_drafts

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 10, 0, tzinfo=UTC)
SINCE = NOW - timedelta(hours=3)


@dataclass
class Row:
    content: str = "What should I read about **black holes**?"
    role: str = "user"
    created_at: datetime = NOW - timedelta(minutes=40)
    id: UUID = UUID(int=3)
    message_metadata: dict[str, Any] | None = None


def test_the_last_recent_question_is_quoted() -> None:
    [draft] = conversation_drafts(Row(), since=SINCE, tz=UTC)
    assert draft.text == (
        "On Saturday 2026-09-26, 09:20, the listener asked LIA: "
        '"What should I read about black holes?"'
    )
    assert (draft.kind, draft.sensitivity) == (FactKind.CONVERSATION, Sensitivity.PERSONAL)


@pytest.mark.parametrize(
    "row",
    [None, Row(created_at=NOW - timedelta(hours=5)), Row(role="assistant"), Row(content=" ")],
)
def test_an_old_absent_or_empty_question_is_no_thread_to_pick_up(row: Row | None) -> None:
    assert conversation_drafts(row, since=SINCE, tz=UTC) == []
