"""Find words across every discussion of an account — one door for the field and the tool.

The chat's history search (QW-2) read ONE discussion, the one on screen. Since
annexes exist (ADR-378), what a person said lives in several discussions, and
neither the search field nor the assistant could find it in another one. This
module is the read both ask — the only one: the history page lost its own word
filter (ADR-378 amendment 2026-11-13):

- the account's own discussions, Main and annexes, that are not deleted — a
  reset already removed its rows (``lifecycle``);
- what the chat shows of them (``visible_only``, ``shown_history_only``): a
  run's hidden rows and blank progress rows are never found;
- the history search's own matching (``matching_content``: case- and
  accent-insensitive, wildcards literal), so the field and the tool can never
  disagree on what « contains » means;
- newest first, the ordering ending on the primary key, resumed by a keyset
  (ADR-185): a page and whether more follow — never a count it did not take.

The assistant's lookup names the run it belongs to: its question is archived
before the run (ADR-117) and would otherwise be its first match.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversation_target import ConversationKind
from src.core.field_names import FIELD_RUN_ID
from src.domains.conversations.message_reads import (
    matching_content,
    older_than,
    shown_history_only,
    visible_only,
)
from src.domains.conversations.models import Conversation, ConversationMessage
from src.infrastructure.database.keyset import Keyset


@dataclass(frozen=True, slots=True)
class DiscussionHit:
    """One message that contains the words, with the discussion it belongs to.

    Attributes:
        message_id: The message.
        role: ``user`` (the person) or ``assistant``.
        content: The message as stored.
        created_at: When it was written (UTC).
        conversation_id: The discussion holding it.
        conversation_kind: Main or an annex.
        conversation_title: The annex's title; None for Main, whose label is
            translated by its reader.
        conversation_revision: The discussion's current generation.
    """

    message_id: UUID
    role: str
    content: str
    created_at: datetime
    conversation_id: UUID
    conversation_kind: ConversationKind
    conversation_title: str | None
    conversation_revision: int


@dataclass(frozen=True, slots=True)
class DiscussionSearchPage:
    """A page of hits, newest first, and whether older ones follow."""

    hits: list[DiscussionHit]
    has_more: bool


async def search_discussions(
    db: AsyncSession,
    user_id: UUID,
    search: str,
    *,
    limit: int,
    before: Keyset | None = None,
    excluding_run: str | None = None,
) -> DiscussionSearchPage:
    """The account's messages that contain ``search``, newest first.

    Args:
        db: A session; the read is one statement, no transaction is kept.
        user_id: The account whose discussions are searched — and no other's.
        search: What to find; a blank term is refused, since it would match
            everything.
        limit: The page size.
        before: Where the page resumes (the last hit served), or None.
        excluding_run: A run whose own rows are left out — the lookup's
            question, archived before it ran.

    Returns:
        The page and whether more hits follow.

    Raises:
        ValueError: ``search`` is blank.
    """
    if not search.strip():
        raise ValueError("a blank search would match every message")
    stmt = (
        select(ConversationMessage, Conversation)
        .join(Conversation, Conversation.id == ConversationMessage.conversation_id)
        .where(Conversation.user_id == user_id, Conversation.deleted_at.is_(None))
    )
    stmt = matching_content(shown_history_only(visible_only(stmt, include_hidden=False)), search)
    if before is not None:
        stmt = older_than(stmt, before.at, before.id)
    if excluding_run:
        stmt = stmt.where(
            ConversationMessage.message_metadata[FIELD_RUN_ID].astext.is_distinct_from(
                excluding_run
            )
        )
    stmt = stmt.order_by(ConversationMessage.created_at.desc(), ConversationMessage.id.desc())
    rows = (await db.execute(stmt.limit(limit + 1))).all()
    hits = [
        DiscussionHit(
            message_id=message.id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
            conversation_id=conversation.id,
            conversation_kind=conversation.kind,
            conversation_title=(
                conversation.title if conversation.kind is ConversationKind.SECONDARY else None
            ),
            conversation_revision=conversation.revision,
        )
        for message, conversation in rows[:limit]
    ]
    return DiscussionSearchPage(hits=hits, has_more=len(rows) > limit)


__all__ = ["DiscussionHit", "DiscussionSearchPage", "search_discussions"]
