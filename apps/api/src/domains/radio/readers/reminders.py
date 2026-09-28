"""The listener's reminders, for the journal's « done » and « ahead » parts (ADR-324 decision 41).

The reminders coming due today come from the Today Briefing's cache (``personal.py``);
what the journal's noon and evening editions add is read here:

- the reminders that RANG today — a reminder that fired leaves its message in the chat
  (``REMINDER_NOTIFICATION_MESSAGE_TYPE``, the scheduler's own stamp), and a consumed
  occurrence is deleted from the reminders table (ADR-268), so the chat is where it is
  read: visible rows only (declared ``VISIBLE_ONLY`` in
  ``conversations/message_readers``), the beginning of what was said, flattened;
- the reminders of the WEEK AHEAD, from tomorrow: the pending rows, soonest first, in
  the window — under the day's own key (``reminder:<id>``), so one the day already
  tells is never retold (``personal_facts``).

Each read opens its own short session and closes it before returning (ADR-304).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta, tzinfo
from typing import Final
from uuid import UUID

from sqlalchemy import select

from src.core.constants import REMINDER_NOTIFICATION_MESSAGE_TYPE
from src.domains.conversations.message_reads import visible_only
from src.domains.conversations.models import ConversationMessage
from src.domains.conversations.repository import ConversationRepository
from src.domains.radio.facts import FactKind, Sensitivity, local_time_text
from src.domains.radio.personal import MAX_PER_SOURCE, JournalPart, PersonalDraft, PersonalSource
from src.domains.radio.readers.messages import MessageRow, excerpt
from src.domains.reminders.repository import ReminderRepository
from src.infrastructure.database.session import get_db_context

#: How far the week ahead reaches, in local days from tomorrow.
AHEAD_DAYS: Final[int] = 7
#: How many pending reminders are read to find the week's (soonest first).
_SCAN_PENDING: Final[int] = 40


@dataclass(frozen=True, slots=True)
class ReminderRing:
    """What the radio reads of one reminder that rang.

    Attributes:
        id: The archived message.
        reminder_id: The reminder, when the message names it.
        rang_at: When it rang (aware).
        excerpt: The beginning of what was said, in plain words.
    """

    id: UUID
    reminder_id: str | None
    rang_at: datetime
    excerpt: str


def ring_line(row: MessageRow) -> ReminderRing | None:
    """An archived message as a reminder that rang, or ``None`` when it is not one."""
    metadata = row.message_metadata or {}
    if row.role != "assistant" or metadata.get("type") != REMINDER_NOTIFICATION_MESSAGE_TYPE:
        return None
    quoted = excerpt(row.content)
    if not quoted:
        return None
    reminder_id = metadata.get("reminder_id")
    return ReminderRing(
        id=row.id,
        reminder_id=str(reminder_id) if reminder_id else None,
        rang_at=row.created_at,
        excerpt=quoted,
    )


def ring_drafts(lines: Sequence[ReminderRing], *, tz: tzinfo) -> list[PersonalDraft]:
    """The reminders that rang, as drafts, in the order given.

    Args:
        lines: The rings of the day, oldest first.
        tz: The listener's timezone.

    Returns:
        One draft per ring.
    """
    return [
        PersonalDraft(
            FactKind.REMINDER,
            f'Reminder rang on {local_time_text(line.rang_at.astimezone(tz))}: "{line.excerpt}"',
            f"done:reminder:{line.reminder_id or line.id}",
            Sensitivity.PERSONAL,
            JournalPart.DONE,
        )
        for line in lines
    ]


@dataclass(frozen=True, slots=True)
class UpcomingReminder:
    """What the radio reads of one pending reminder.

    Attributes:
        id: The reminder.
        content: What it will say.
        trigger_at: When it will ring (aware).
    """

    id: UUID
    content: str
    trigger_at: datetime


def upcoming_drafts(
    lines: Sequence[UpcomingReminder], *, now: datetime, tz: tzinfo
) -> list[PersonalDraft]:
    """The reminders of the week ahead, from tomorrow, as drafts.

    Args:
        lines: The pending reminders, soonest first.
        now: The current instant (aware).
        tz: The listener's timezone.

    Returns:
        One draft per reminder ringing between tomorrow and ``AHEAD_DAYS`` days on.
    """
    today = now.astimezone(tz).date()
    first, last = today + timedelta(days=1), today + timedelta(days=AHEAD_DAYS)
    drafts: list[PersonalDraft] = []
    for line in lines:
        when = line.trigger_at.astimezone(tz)
        if not first <= when.date() <= last:
            continue
        drafts.append(
            PersonalDraft(
                FactKind.REMINDER,
                f"Reminder on {local_time_text(when)}: {line.content}",
                f"reminder:{line.id}",
                Sensitivity.PERSONAL,
                JournalPart.AHEAD,
            )
        )
    return drafts


async def read_reminders_done(user_id: UUID, *, now: datetime, tz: tzinfo) -> list[PersonalDraft]:
    """The reminders that rang today, oldest first, read from the chat where they rang.

    Args:
        user_id: The listener.
        now: The current instant (aware).
        tz: The listener's timezone.

    Returns:
        The drafts, bounded like every personal source.
    """
    since = datetime.combine(now.astimezone(tz).date(), time(), tzinfo=tz)
    kind = ConversationMessage.message_metadata["type"].astext
    async with get_db_context() as db:
        conversation = await ConversationRepository(db).get_active_for_user(user_id)
        if conversation is None:
            return []
        stmt = visible_only(
            select(ConversationMessage).where(
                ConversationMessage.conversation_id == conversation.id,
                ConversationMessage.created_at >= since,
                ConversationMessage.role == "assistant",
                kind == REMINDER_NOTIFICATION_MESSAGE_TYPE,
            ),
            include_hidden=False,
        ).order_by(ConversationMessage.created_at.asc(), ConversationMessage.id.asc())
        rows = (await db.execute(stmt.limit(MAX_PER_SOURCE[PersonalSource.REMINDERS]))).scalars()
        lines = [line for row in rows if (line := ring_line(row)) is not None]
    return ring_drafts(lines, tz=tz)


async def read_reminders_ahead(user_id: UUID, *, now: datetime, tz: tzinfo) -> list[PersonalDraft]:
    """The reminders of the week ahead, from tomorrow, soonest first.

    Args:
        user_id: The listener.
        now: The current instant (aware).
        tz: The listener's timezone.

    Returns:
        The drafts, bounded like every personal source.
    """
    async with get_db_context() as db:
        rows = await ReminderRepository(db).get_pending_for_user(user_id, limit=_SCAN_PENDING)
        lines = [
            UpcomingReminder(id=row.id, content=row.content, trigger_at=row.trigger_at)
            for row in rows
        ]
    return upcoming_drafts(lines, now=now, tz=tz)[: MAX_PER_SOURCE[PersonalSource.REMINDERS]]


__all__ = [
    "AHEAD_DAYS",
    "ReminderRing",
    "UpcomingReminder",
    "read_reminders_ahead",
    "read_reminders_done",
    "ring_drafts",
    "ring_line",
    "upcoming_drafts",
]
