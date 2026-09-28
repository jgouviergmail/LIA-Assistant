"""The reminders for the journal: the ones that rang today, the ones of the week ahead."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import pytest

from src.core.constants import REMINDER_NOTIFICATION_MESSAGE_TYPE
from src.domains.radio.facts import FactKind
from src.domains.radio.personal import JournalPart
from src.domains.radio.readers.reminders import (
    AHEAD_DAYS,
    ReminderRing,
    UpcomingReminder,
    ring_drafts,
    ring_line,
    upcoming_drafts,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 13, 0, tzinfo=UTC)  # Saturday
PLUS_TWO = timezone(timedelta(hours=2))


@dataclass(frozen=True)
class Row:
    id: UUID
    role: str
    content: str
    message_metadata: dict[str, Any] | None
    created_at: datetime


def row(n: int, *, kind: str = REMINDER_NOTIFICATION_MESSAGE_TYPE, role: str = "assistant") -> Row:
    return Row(
        id=UUID(int=n),
        role=role,
        content="🔔 **Call the plumber** — you asked at 09:00.",
        message_metadata={"type": kind, "reminder_id": f"r{n}"},
        created_at=NOW - timedelta(hours=n),
    )


class TestRings:
    def test_a_reminder_s_message_is_a_ring_read_in_plain_words(self) -> None:
        line = ring_line(row(1))
        assert line == ReminderRing(
            id=UUID(int=1),
            reminder_id="r1",
            rang_at=NOW - timedelta(hours=1),
            excerpt="🔔 Call the plumber — you asked at 09:00.",
        )

    def test_another_message_is_no_ring(self) -> None:
        assert ring_line(row(2, kind="proactive_interest")) is None
        assert ring_line(row(3, role="user")) is None
        assert (
            ring_line(
                Row(UUID(int=4), "assistant", "", {"type": REMINDER_NOTIFICATION_MESSAGE_TYPE}, NOW)
            )
            is None
        )

    def test_a_ring_is_a_done_fact_under_its_reminder_s_key_on_the_listener_s_clock(self) -> None:
        line = ring_line(row(1))
        assert line is not None
        [draft] = ring_drafts([line], tz=PLUS_TWO)
        assert (
            draft.text
            == 'Reminder rang on Saturday 2026-09-26, 14:00: "🔔 Call the plumber — you asked at 09:00."'
        )
        assert (draft.kind, draft.part, draft.key) == (
            FactKind.REMINDER,
            JournalPart.DONE,
            "done:reminder:r1",
        )
        nameless = ReminderRing(id=UUID(int=9), reminder_id=None, rang_at=NOW, excerpt="x")
        assert ring_drafts([nameless], tz=UTC)[0].key == f"done:reminder:{UUID(int=9)}"


class TestUpcoming:
    def test_the_week_ahead_starts_tomorrow_and_keeps_the_day_s_key(self) -> None:
        def at(days: int, hour: int = 18) -> UpcomingReminder:
            return UpcomingReminder(
                id=UUID(int=days),
                content=f"in {days} days",
                trigger_at=NOW.replace(hour=hour) + timedelta(days=days),
            )

        drafts = upcoming_drafts(
            [at(0), at(1), at(AHEAD_DAYS), at(AHEAD_DAYS + 1)], now=NOW, tz=UTC
        )
        assert [d.key for d in drafts] == [
            f"reminder:{UUID(int=1)}",
            f"reminder:{UUID(int=AHEAD_DAYS)}",
        ]
        assert drafts[0].text == "Reminder on Sunday 2026-09-27, 18:00: in 1 days"
        assert {d.part for d in drafts} == {JournalPart.AHEAD}

    def test_the_day_is_the_listener_s(self) -> None:
        tonight = UpcomingReminder(
            id=UUID(int=1), content="late", trigger_at=datetime(2026, 9, 26, 23, 30, tzinfo=UTC)
        )
        assert upcoming_drafts([tonight], now=NOW, tz=UTC) == []
        [east] = upcoming_drafts([tonight], now=NOW, tz=PLUS_TWO)
        assert east.text.startswith("Reminder on Sunday 2026-09-27, 01:30")
