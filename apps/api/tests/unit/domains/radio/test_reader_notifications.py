"""Notifications LIA sent: only hers, of her own initiative, quoted briefly in plain words."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from src.domains.radio.facts import FactKind, Sensitivity
from src.domains.radio.readers.messages import EXCERPT_MAX_CHARS
from src.domains.radio.readers.notifications import notification_drafts, notification_line

pytestmark = pytest.mark.unit

SENT = datetime(2026, 9, 26, 6, 12, tzinfo=UTC)


@dataclass
class Row:
    content: str
    message_metadata: dict[str, Any] | None = field(
        default_factory=lambda: {"type": "proactive_interest_update"}
    )
    role: str = "assistant"
    id: UUID = UUID(int=7)
    created_at: datetime = SENT


def test_a_notification_is_quoted_in_plain_words_with_its_topic() -> None:
    line = notification_line(Row("<p>New on <b>black holes</b>:</p>\n\n- a **paper**"))
    assert line is not None
    [draft] = notification_drafts([line], tz=UTC)
    assert draft.text == (
        "LIA sent the listener a notification (interest update) on "
        'Saturday 2026-09-26, 06:12: "New on black holes: • a paper"'
    )
    assert (draft.kind, draft.key, draft.sensitivity) == (
        FactKind.NOTIFICATION,
        f"notification:{UUID(int=7)}",
        Sensitivity.PERSONAL,
    )


def test_a_long_notification_is_cut_at_a_word() -> None:
    line = notification_line(Row("word " * 200))
    assert line is not None
    assert len(line.excerpt) <= EXCERPT_MAX_CHARS and line.excerpt.endswith("word…")


@pytest.mark.parametrize(
    "row",
    [
        Row("Hello", role="user"),  # the person's own words
        Row("Hello", message_metadata={"type": "live_turn"}),  # a spoken exchange
        Row("Hello", message_metadata=None),  # an ordinary answer
        Row("   "),  # nothing to quote
    ],
)
def test_only_lia_s_own_notifications_speak(row: Row) -> None:
    assert notification_line(row) is None
