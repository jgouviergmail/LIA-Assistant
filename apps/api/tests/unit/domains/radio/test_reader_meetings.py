"""Recent meetings: ready ones only, the edited minutes first, what was decided to be done."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import pytest

from src.domains.meetings.models import MeetingStatus
from src.domains.radio.facts import FactKind, Sensitivity
from src.domains.radio.readers.meetings import meeting_drafts, meeting_line

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 7, 0, tzinfo=UTC)
SINCE = NOW - timedelta(hours=36)


def minutes(title: str, *actions: dict[str, str]) -> dict[str, Any]:
    return {
        "title": title,
        "participants": [],
        "sections": [
            {"key": "summary", "label": "Summary", "kind": "paragraph", "paragraph": "We met."},
            {
                "key": "actions",
                "label": "Actions",
                "kind": "action_items",
                "action_items": list(actions),
            },
        ],
    }


@dataclass
class Row:
    id: UUID = UUID(int=1)
    status: MeetingStatus = MeetingStatus.READY
    started_at: datetime = NOW - timedelta(hours=18)
    report_current: dict[str, Any] | None = None
    report_generated: dict[str, Any] | None = None


def test_it_says_what_was_decided_to_be_done_by_whom_and_when() -> None:
    row = Row(
        report_generated=minutes(
            "Budget review",
            {"description": "Send the figures", "owner": "Alex", "due_date": "2026-09-30"},
            {"description": "Book a room"},
            {"description": "Call the bank", "owner": "Sam"},
            {"description": "Update the plan"},
        )
    )
    line = meeting_line(row, since=SINCE)
    assert line is not None
    [draft] = meeting_drafts([line], tz=timezone(timedelta(hours=2)))
    assert draft.text == (
        'Meeting "Budget review" (Friday 2026-09-25, 15:00): 4 action items — '
        "Alex: Send the figures (due 2026-09-30); Book a room; Sam: Call the bank"
    )
    assert (draft.kind, draft.key, draft.sensitivity) == (
        FactKind.MEETING,
        f"meeting:{UUID(int=1)}",
        Sensitivity.PERSONAL,
    )


def test_the_minutes_the_person_edited_win() -> None:
    row = Row(
        report_generated=minutes("Generated title"),
        report_current=minutes("The title the person kept"),
    )
    line = meeting_line(row, since=SINCE)
    assert line is not None and line.report.title == "The title the person kept"


@pytest.mark.parametrize(
    "row",
    [
        Row(status=MeetingStatus.PROCESSING, report_generated=minutes("Not yet")),
        Row(started_at=NOW - timedelta(days=3), report_generated=minutes("Too old")),
        Row(report_generated={"title": ""}),  # minutes this release cannot read
        Row(),  # no minutes at all
    ],
)
def test_a_meeting_with_nothing_to_say_is_skipped(row: Row) -> None:
    assert meeting_line(row, since=SINCE) is None


def test_minutes_without_actions_say_so() -> None:
    line = meeting_line(Row(report_generated=minutes("Catch-up")), since=SINCE)
    assert line is not None
    [draft] = meeting_drafts([line], tz=UTC)
    assert draft.text.endswith(": no action item in the minutes")
