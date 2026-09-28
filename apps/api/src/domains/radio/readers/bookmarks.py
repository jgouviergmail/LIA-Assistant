"""Answers the listener kept lately, for the personal corner.

A bookmark is an answer the person chose to keep (ADR-282): the station may
come back to one they kept this week — « on Tuesday you kept LIA's answer
about… ». It is named by the REQUEST that produced it (the person's own words),
or by the beginning of the answer when no request precedes it (a notification
they kept).

The bookmarks page is ordered by the ANSWER's date (ADR-282); the radio reads
its newest rows and keeps those the person kept in the last week — a bookmark
of an old answer, kept today, sits further down that page and is not looked
for past it (the end of the read is stated, never implied).

The read opens its own short session and closes it before returning (ADR-304).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from typing import Final, Protocol
from uuid import UUID

from src.domains.bookmarks.queries import BookmarkFilters
from src.domains.bookmarks.repository import BookmarkRepository
from src.domains.radio.facts import FactKind, Sensitivity, local_time_text
from src.domains.radio.personal import MAX_PER_SOURCE, PersonalDraft, PersonalSource
from src.domains.radio.readers.messages import excerpt
from src.infrastructure.database.session import get_db_context

#: How far back a kept answer is still « lately ».
BOOKMARK_RECENT_DAYS: Final[int] = 7
#: How many of the newest rows are read to find them.
_SCAN_ROWS: Final[int] = 10


class BookmarkRow(Protocol):
    """The columns of a bookmark the radio reads."""

    @property
    def id(self) -> UUID: ...

    @property
    def created_at(self) -> datetime: ...

    @property
    def request_content(self) -> str | None: ...

    @property
    def content(self) -> str: ...


@dataclass(frozen=True, slots=True)
class KeptAnswer:
    """A kept answer as the radio names it.

    Attributes:
        id: The bookmark.
        kept_at: When the person kept it (aware).
        about: What it answers, in plain words.
        by_request: Whether ``about`` quotes the person's request.
    """

    id: UUID
    kept_at: datetime
    about: str
    by_request: bool


def kept_answers(rows: Sequence[BookmarkRow], *, since: datetime) -> list[KeptAnswer]:
    """The bookmarks kept after ``since`` that say something, newest kept first."""
    kept: list[KeptAnswer] = []
    for row in rows:
        if row.created_at < since:
            continue
        request = excerpt(row.request_content or "")
        about = request or excerpt(row.content)
        if about:
            kept.append(KeptAnswer(row.id, row.created_at, about, by_request=bool(request)))
    return sorted(kept, key=lambda answer: answer.kept_at, reverse=True)


def bookmark_drafts(answers: Sequence[KeptAnswer], *, tz: tzinfo) -> list[PersonalDraft]:
    """The kept answers as drafts."""
    drafts: list[PersonalDraft] = []
    for answer in answers:
        when = local_time_text(answer.kept_at.astimezone(tz))
        what = "LIA's answer to" if answer.by_request else "an answer of LIA's that begins"
        drafts.append(
            PersonalDraft(
                FactKind.BOOKMARK,
                f'On {when}, the listener kept {what}: "{answer.about}"',
                f"bookmark:{answer.id}",
                Sensitivity.PERSONAL,
            )
        )
    return drafts


async def read_bookmarks(user_id: UUID, *, now: datetime, tz: tzinfo) -> list[PersonalDraft]:
    """The answers kept this week.

    Args:
        user_id: The listener.
        now: The current instant (aware).
        tz: The listener's timezone.

    Returns:
        The drafts, bounded like every personal source.
    """
    async with get_db_context() as db:
        rows, _total = await BookmarkRepository(db).list_page(
            user_id, BookmarkFilters(limit=_SCAN_ROWS)
        )
        answers = kept_answers(rows, since=now - timedelta(days=BOOKMARK_RECENT_DAYS))
    return bookmark_drafts(answers[: MAX_PER_SOURCE[PersonalSource.BOOKMARKS]], tz=tz)


__all__ = [
    "BOOKMARK_RECENT_DAYS",
    "KeptAnswer",
    "bookmark_drafts",
    "kept_answers",
    "read_bookmarks",
]
