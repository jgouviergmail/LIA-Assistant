"""The tasks for the journal: ticked today on the listener's clock, due in the week ahead."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from src.domains.radio.facts import FactKind
from src.domains.radio.personal import JournalPart
from src.domains.radio.readers.tasks import (
    AHEAD_DAYS,
    TaskLine,
    task_line,
    tasks_ahead_drafts,
    tasks_done_drafts,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 13, 0, tzinfo=UTC)  # Saturday
PLUS_TWO = timezone(timedelta(hours=2))


def task(
    n: int,
    *,
    completed: bool = False,
    due: date | None = None,
    completed_at: datetime | None = None,
    with_id: bool = True,
) -> TaskLine:
    return TaskLine(
        id=f"t{n}" if with_id else None,
        title=f"Task {n}",
        completed=completed,
        due=due,
        completed_at=completed_at,
    )


class TestDone:
    def test_a_task_ticked_today_is_done_with_its_time(self) -> None:
        [draft] = tasks_done_drafts(
            [task(1, completed=True, completed_at=NOW - timedelta(hours=3))], now=NOW, tz=UTC
        )
        assert draft.text == 'Task "Task 1" completed today at 10:00'
        assert (draft.kind, draft.part, draft.key) == (
            FactKind.TASK,
            JournalPart.DONE,
            "done:task:t1",
        )

    def test_the_day_is_the_listener_s(self) -> None:
        # 23:30 UTC yesterday is 01:30 today two hours east.
        late = task(2, completed=True, completed_at=datetime(2026, 9, 25, 23, 30, tzinfo=UTC))
        assert tasks_done_drafts([late], now=NOW, tz=UTC) == []
        [east] = tasks_done_drafts([late], now=NOW, tz=PLUS_TWO)
        assert east.text.endswith("completed today at 01:30")

    def test_an_open_task_or_one_ticked_at_an_unknown_time_is_not_done(self) -> None:
        open_task = task(3, due=NOW.date())
        unknown = task(4, completed=True, completed_at=None)
        assert tasks_done_drafts([open_task, unknown], now=NOW, tz=UTC) == []


class TestAhead:
    def test_the_week_ahead_starts_tomorrow_and_keeps_the_day_s_key(self) -> None:
        today = NOW.date()
        drafts = tasks_ahead_drafts(
            [
                task(1, due=today),  # today's: the day tells it
                task(2, due=today + timedelta(days=1)),
                task(3, due=today + timedelta(days=AHEAD_DAYS)),
                task(4, due=today + timedelta(days=AHEAD_DAYS + 1)),
                task(5, due=None),
                task(6, completed=True, due=today + timedelta(days=2)),
            ],
            now=NOW,
            tz=UTC,
        )
        assert [d.key for d in drafts] == ["task:t2", "task:t3"]
        assert drafts[0].text == 'Task "Task 2" is due on Sunday 2026-09-27'
        assert {d.part for d in drafts} == {JournalPart.AHEAD}

    def test_without_an_id_the_key_is_a_digest_of_the_title(self) -> None:
        [draft] = tasks_ahead_drafts(
            [task(7, due=NOW.date() + timedelta(days=3), with_id=False)], now=NOW, tz=UTC
        )
        assert draft.key.startswith("task:") and draft.key != "task:"


def test_a_provider_task_is_read_in_the_google_shape_every_client_normalises_to() -> None:
    line = task_line(
        {
            "id": "abc",
            "title": "  Renew the lease ",
            "status": "completed",
            "due": "2026-09-30T00:00:00.000Z",
            "completed": "2026-09-26T09:12:00.000Z",
        }
    )
    assert line == TaskLine(
        id="abc",
        title="Renew the lease",
        completed=True,
        due=date(2026, 9, 30),
        completed_at=datetime(2026, 9, 26, 9, 12, tzinfo=UTC),
    )
    bare = task_line({"status": "needsAction", "due": "not a date"})
    assert bare == TaskLine(id=None, title="Untitled", completed=False, due=None, completed_at=None)
