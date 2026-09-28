"""The listener's recent meetings, as drafts for the personal corner.

A meeting the recorder turned into minutes (ADR-258) in the last day and a half
becomes one fact: its title, when it took place in the listener's own time, and
what was decided to be done — the action items, with who and by when when the
minutes name them. The minutes the person EDITED win over the generated ones:
the radio says what the person kept, never a version they corrected.

Only a READY meeting speaks (a meeting still recording or processing has no
minutes yet), and minutes this release cannot read are skipped, never guessed.
The read opens its own short session and closes it before returning (ADR-304).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from typing import Any, Final, Protocol
from uuid import UUID

from pydantic import ValidationError

from src.domains.meetings.models import MeetingStatus
from src.domains.meetings.repository import MeetingRepository
from src.domains.meetings.schemas import ActionItem, MeetingReport, SectionKind
from src.domains.radio.facts import FactKind, Sensitivity, local_time_text
from src.domains.radio.personal import MAX_PER_SOURCE, PersonalDraft, PersonalSource
from src.infrastructure.database.session import get_db_context

#: How far back a meeting is still « recent » for the radio.
MEETING_RECENT_HOURS: Final[int] = 36
#: How many action items one meeting's fact names (the count covers them all).
ACTIONS_NAMED_MAX: Final[int] = 3
#: How many rows are read to find the recent ready ones (newest first).
_SCAN_ROWS: Final[int] = 10


@dataclass(frozen=True, slots=True)
class MeetingLine:
    """What the radio reads of one meeting.

    Attributes:
        id: The meeting.
        started_at: When it started (aware).
        report: Its minutes.
    """

    id: UUID
    started_at: datetime
    report: MeetingReport


def _action(item: ActionItem) -> str:
    text = item.description.strip()
    if item.owner:
        text = f"{item.owner.strip()}: {text}"
    if item.due_date:
        text += f" (due {item.due_date.strip()})"
    return text


def meeting_drafts(meetings: Sequence[MeetingLine], *, tz: tzinfo) -> list[PersonalDraft]:
    """The meetings as drafts, newest first.

    Args:
        meetings: The recent ready meetings.
        tz: The listener's timezone.

    Returns:
        One draft per meeting.
    """
    drafts: list[PersonalDraft] = []
    for meeting in meetings:
        actions = [
            item
            for section in meeting.report.sections
            if section.kind is SectionKind.ACTION_ITEMS
            for item in section.action_items
        ]
        when = local_time_text(meeting.started_at.astimezone(tz))
        text = f'Meeting "{meeting.report.title}" ({when})'
        if actions:
            named = "; ".join(_action(item) for item in actions[:ACTIONS_NAMED_MAX])
            text += f": {len(actions)} action items — {named}"
        else:
            text += ": no action item in the minutes"
        drafts.append(
            PersonalDraft(FactKind.MEETING, text, f"meeting:{meeting.id}", Sensitivity.PERSONAL)
        )
    return drafts


class MeetingRow(Protocol):
    """The columns of a stored meeting the radio reads."""

    @property
    def id(self) -> UUID: ...

    @property
    def status(self) -> MeetingStatus: ...

    @property
    def started_at(self) -> datetime: ...

    @property
    def report_current(self) -> dict[str, Any] | None: ...

    @property
    def report_generated(self) -> dict[str, Any] | None: ...


def meeting_line(row: MeetingRow, *, since: datetime) -> MeetingLine | None:
    """A stored meeting as the radio reads it, or None when it has nothing to say.

    Only a READY meeting started after ``since`` speaks; the minutes the person
    edited win over the generated ones, and minutes this release cannot read
    are skipped rather than guessed.
    """
    if row.status != MeetingStatus.READY or row.started_at < since:
        return None
    raw = row.report_current if row.report_current is not None else row.report_generated
    if raw is None:
        return None
    try:
        report = MeetingReport.model_validate(raw)
    except ValidationError:
        return None
    return MeetingLine(id=row.id, started_at=row.started_at, report=report)


async def read_meetings(user_id: UUID, *, now: datetime, tz: tzinfo) -> list[PersonalDraft]:
    """The listener's recent ready meetings, read from their minutes.

    Args:
        user_id: The listener.
        now: The current instant (aware).
        tz: The listener's timezone.

    Returns:
        The drafts, bounded like every personal source.
    """
    since = now - timedelta(hours=MEETING_RECENT_HOURS)
    async with get_db_context() as db:
        rows, _total = await MeetingRepository(db).list_for_user(
            user_id, limit=_SCAN_ROWS, offset=0
        )
        lines = [line for row in rows if (line := meeting_line(row, since=since)) is not None]
    return meeting_drafts(lines[: MAX_PER_SOURCE[PersonalSource.MEETINGS]], tz=tz)


__all__ = [
    "MEETING_RECENT_HOURS",
    "MeetingLine",
    "MeetingRow",
    "meeting_drafts",
    "meeting_line",
    "read_meetings",
]
