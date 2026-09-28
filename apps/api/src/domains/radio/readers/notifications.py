"""The notifications LIA sent the listener lately, as drafts for the personal corner.

What LIA said of her own initiative in the last day — an interest update, a
birthday, a heartbeat — is read from the conversation where it was archived:
visible rows only (declared ``VISIBLE_ONLY`` in ``conversations/message_readers``
— a hidden run row is not something the person was told), the NEWEST end of the
day kept (a capped read states which end it keeps), the ``proactive_`` prefix
matched literally (its ``_`` is a LIKE wildcard). The station may come back to
one of them; it quotes the beginning of what was said, flattened to plain words
(the archived text is Markdown or HTML). A message or an image a connection
sent through LIA is theirs, not LIA's: the query leaves it out
(``peers.RELAYED_MESSAGE_TYPES``, owner decision 2026-09-27).

A news flash reads the same rows from the other end (ADR-324 decision 32): what
LIA wrote AFTER the station last looked, oldest first, so a flash tells them in
the order they were sent and the next one starts where it stopped.

The read opens its own short session and closes it before returning (ADR-304).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from typing import Final
from uuid import UUID

from sqlalchemy import Select, select

from src.core.constants import PROACTIVE_MESSAGE_TYPE_PREFIX
from src.domains.conversations.message_reads import visible_only
from src.domains.conversations.models import ConversationMessage
from src.domains.conversations.repository import ConversationRepository
from src.domains.peers.constants import RELAYED_MESSAGE_TYPES
from src.domains.radio.facts import FactKind, Sensitivity, local_time_text, notification_key
from src.domains.radio.flash import FlashNote
from src.domains.radio.personal import MAX_PER_SOURCE, PersonalDraft, PersonalSource
from src.domains.radio.readers.messages import MessageRow, excerpt
from src.infrastructure.database.session import get_db_context

#: How far back a notification is still worth coming back to.
NOTIFICATION_RECENT_HOURS: Final[int] = 24


@dataclass(frozen=True, slots=True)
class NotificationLine:
    """What the radio reads of one notification.

    Attributes:
        id: The archived message.
        sent_at: When it was sent (aware).
        topic: What kind of notification it was (``interest``, ``birthday``…).
        excerpt: The beginning of what was said, in plain words.
    """

    id: UUID
    sent_at: datetime
    topic: str
    excerpt: str


def notification_line(row: MessageRow) -> NotificationLine | None:
    """An archived message as a notification the radio may come back to, or None."""
    kind = (row.message_metadata or {}).get("type")
    if row.role != "assistant" or not isinstance(kind, str):
        return None
    if not kind.startswith(PROACTIVE_MESSAGE_TYPE_PREFIX):
        return None
    quoted = excerpt(row.content)
    if not quoted:
        return None
    topic = kind[len(PROACTIVE_MESSAGE_TYPE_PREFIX) :].replace("_", " ") or "update"
    return NotificationLine(id=row.id, sent_at=row.created_at, topic=topic, excerpt=quoted)


def notification_drafts(lines: Sequence[NotificationLine], *, tz: tzinfo) -> list[PersonalDraft]:
    """The notifications as drafts, in the order given.

    Args:
        lines: The notifications, newest first.
        tz: The listener's timezone.

    Returns:
        One draft per notification.
    """
    return [
        PersonalDraft(
            FactKind.NOTIFICATION,
            f"LIA sent the listener a notification ({line.topic}) on "
            f'{local_time_text(line.sent_at.astimezone(tz))}: "{line.excerpt}"',
            notification_key(line.id),
            Sensitivity.PERSONAL,
        )
        for line in lines
    ]


def _sent_after(conversation_id: UUID, after: datetime) -> Select[tuple[ConversationMessage]]:
    """The visible notifications of a conversation archived after ``after``."""
    kind = ConversationMessage.message_metadata["type"].astext
    return visible_only(
        select(ConversationMessage).where(
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.created_at > after,
            ConversationMessage.role == "assistant",
            kind.startswith(PROACTIVE_MESSAGE_TYPE_PREFIX, autoescape=True),
            kind.not_in(sorted(RELAYED_MESSAGE_TYPES)),
        ),
        include_hidden=False,
    )


async def _lines(
    user_id: UUID, *, after: datetime, newest_first: bool, limit: int
) -> list[NotificationLine]:
    """The listener's notifications after ``after``, from the end asked for, bounded."""
    order = (
        (ConversationMessage.created_at.desc(), ConversationMessage.id.desc())
        if newest_first
        else (ConversationMessage.created_at.asc(), ConversationMessage.id.asc())
    )
    async with get_db_context() as db:
        conversation = await ConversationRepository(db).get_active_for_user(user_id)
        if conversation is None:
            return []
        stmt = _sent_after(conversation.id, after).order_by(*order).limit(limit)
        rows = (await db.execute(stmt)).scalars().all()
    return [line for row in rows if (line := notification_line(row)) is not None]


async def read_notifications(user_id: UUID, *, now: datetime, tz: tzinfo) -> list[PersonalDraft]:
    """The notifications of the last day, newest first.

    Args:
        user_id: The listener.
        now: The current instant (aware).
        tz: The listener's timezone.

    Returns:
        The drafts, bounded like every personal source.
    """
    lines = await _lines(
        user_id,
        after=now - timedelta(hours=NOTIFICATION_RECENT_HOURS),
        newest_first=True,
        limit=MAX_PER_SOURCE[PersonalSource.NOTIFICATIONS],
    )
    return notification_drafts(lines, tz=tz)


async def read_flash_notes(user_id: UUID, *, after: datetime, limit: int) -> list[FlashNote]:
    """What LIA wrote to the listener after ``after``, oldest first — a flash's material.

    Args:
        user_id: The listener.
        after: The flash watermark (the session's start, then the newest note taken).
        limit: The most notes one flash tells.

    Returns:
        The notes, in the order they were sent.
    """
    lines = await _lines(user_id, after=after, newest_first=False, limit=limit)
    return [
        FlashNote(id=str(line.id), sent_at=line.sent_at, topic=line.topic, excerpt=line.excerpt)
        for line in lines
    ]


__all__ = [
    "NOTIFICATION_RECENT_HOURS",
    "NotificationLine",
    "notification_drafts",
    "notification_line",
    "read_flash_notes",
    "read_notifications",
]
