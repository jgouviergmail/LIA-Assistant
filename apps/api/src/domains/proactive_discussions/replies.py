"""Bind genuine archived replies to durable openings; no duplicated human content.

A reply belongs to the opening it answered only while that opening was still open
(ADR-358: a late, unrelated message is never attached to it). Until memory
extraction acknowledges it, the reply is a transient guard on later runs
(ADR-359), bounded in time so an extraction that never comes can neither hold
the producer for ever nor turn into permanent learning.
"""

from datetime import datetime, timedelta
from functools import lru_cache
from html import escape
from uuid import UUID

from sqlalchemy import ColumnElement, String, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.field_names import FIELD_IS_AUTOMATED_SOURCE
from src.core.prompt_store import parse_prompt_sections, read_prompt_file
from src.core.token_budget import count_external_tokens
from src.domains.conversations.models import ConversationMessage
from src.domains.proactive_discussions.models import DiscussionOpeningRecord, DiscussionPreference
from src.domains.proactive_discussions.policy_repository import DiscussionPolicyRepository
from src.domains.proactive_discussions.rule_controls import ControlSupport
from src.domains.shared.discussion_directives import DirectiveBudgetExceeded

REPLY_TO = "proactive_discussion_reply_to"
CONTROLS_APPLIED = "proactive_discussion_controls_applied"


@lru_cache(maxsize=1)
def _control_lines() -> dict[str, str]:
    """One-line scaffolds of the control snapshot, read once from the prompt store."""
    return dict(parse_prompt_sections(read_prompt_file("discussion_control_lines"), 2))


async def synchronize_replies(db: AsyncSession, owner: UUID, *, now: datetime) -> None:
    """Attach the first genuine reply to the pending opening, or let it expire.

    Args:
        db: The caller's session (rows are locked, never committed here).
        owner: The account whose opening is settled.
        now: The caller's clock; an opening past its deadline with no reply expires.
    """
    await DiscussionPolicyRepository(db)._owner(owner)
    preference = await db.scalar(
        select(DiscussionPreference.id)
        .where(DiscussionPreference.user_id == owner)
        .with_for_update()
    )
    if preference is None:
        return
    opening = await db.scalar(
        select(DiscussionOpeningRecord)
        .where(DiscussionOpeningRecord.user_id == owner, DiscussionOpeningRecord.state == "pending")
        .with_for_update()
    )
    if opening is None:
        return
    reply = await db.scalar(
        select(ConversationMessage)
        .where(*_reply_to(opening))
        .order_by(ConversationMessage.created_at, ConversationMessage.id)
        .limit(1)
    )
    if reply is not None:
        reply.message_metadata = {**(reply.message_metadata or {}), REPLY_TO: str(opening.id)}
        opening.state = "engaged"
    elif opening.expires_at <= now:
        opening.state = "expired"
    await db.flush()


def _reply_to(opening: DiscussionOpeningRecord) -> tuple[ColumnElement[bool], ...]:
    """What makes a message a genuine reply to ``opening``: one predicate, two readers.

    The person's own visible words in its conversation, written while it was open
    (a later message answers something else), never a routine's question.
    """
    return (
        ConversationMessage.conversation_id == opening.conversation_id,
        ConversationMessage.role == "user",
        ConversationMessage.hidden.is_(False),
        ConversationMessage.message_metadata[CONTROLS_APPLIED].astext.is_distinct_from("true"),
        ConversationMessage.created_at > opening.created_at,
        ConversationMessage.created_at <= opening.expires_at,
        ConversationMessage.message_metadata[FIELD_IS_AUTOMATED_SOURCE].astext.is_distinct_from(
            "true"
        ),
    )


async def has_reply(db: AsyncSession, opening: DiscussionOpeningRecord) -> bool:
    """Whether the person answered ``opening``, even by a reply not bound to it yet.

    A read: only :func:`synchronize_replies` binds a reply.

    Args:
        db: The session to read with.
        opening: The opening.

    Returns:
        True when a genuine reply exists.
    """
    return (
        await db.scalar(select(ConversationMessage.id).where(*_reply_to(opening)).limit(1))
    ) is not None


async def pending_controls(
    db: AsyncSession, owner: UUID, *, memory_enabled: bool, now: datetime
) -> tuple[ControlSupport, ...]:
    """Every live reply guard memory has not acknowledged, complete or refused.

    Args:
        db: The caller's session.
        owner: The account whose guards are read.
        memory_enabled: The person's memory consent; without it nothing is retained.
        now: The caller's clock, bounding a guard's life.

    Returns:
        The live guards, newest first.

    Raises:
        DirectiveBudgetExceeded: When the live guards cannot all fit their budget
            (``discussion_reply_guard_max_rows`` and ``_max_tokens``): a complete
            guard set or none (ADR-359).
    """
    if not memory_enabled:
        return ()
    oldest = now - timedelta(hours=settings.discussion_reply_guard_ttl_hours)
    rows_max = settings.discussion_reply_guard_max_rows
    query = (
        select(ConversationMessage.id, ConversationMessage.content)
        .join(
            DiscussionOpeningRecord,
            DiscussionOpeningRecord.id.cast(String)
            == ConversationMessage.message_metadata[REPLY_TO].astext,
        )
        .where(
            DiscussionOpeningRecord.user_id == owner,
            ConversationMessage.conversation_id == DiscussionOpeningRecord.conversation_id,
            ConversationMessage.role == "user",
            ConversationMessage.hidden.is_(False),
            ConversationMessage.message_metadata[CONTROLS_APPLIED].astext.is_distinct_from("true"),
            ConversationMessage.message_metadata[FIELD_IS_AUTOMATED_SOURCE].astext.is_distinct_from(
                "true"
            ),
            ConversationMessage.created_at > oldest,
        )
        .order_by(ConversationMessage.created_at.desc())
        .limit(rows_max + 1)
    )
    rows = (await db.execute(query)).tuples().all()
    if len(rows) > rows_max:
        raise DirectiveBudgetExceeded("reply-control work budget exceeded")
    supports = tuple(
        ControlSupport(id=f"reply:{key}", text=body) for key, body in rows if body.strip()
    )
    text = render_pending_controls(supports)
    if count_external_tokens(text) > settings.discussion_reply_guard_max_tokens:
        raise DirectiveBudgetExceeded("complete pending reply controls exceed their budget")
    return supports


def render_pending_controls(supports: tuple[ControlSupport, ...]) -> str:
    """The guards as one tagged block, or nothing at all when there is none."""
    if not supports:
        return ""
    text = "\n".join(f'<reply id="{item.id}">{escape(item.text)}</reply>' for item in supports)
    return f"<reply_controls>{_control_lines()['reply_controls']}\n{text}</reply_controls>"


async def correction_guard(
    db: AsyncSession, owner: UUID, *, memory_enabled: bool, now: datetime
) -> str:
    """The rendered guard block a run reads beside the person's directives."""
    return render_pending_controls(
        await pending_controls(db, owner, memory_enabled=memory_enabled, now=now)
    )


async def acknowledge_reply(db: AsyncSession, owner: UUID, run_id: str, *, now: datetime) -> None:
    """Clear the guard of the reply memory extraction just processed (its run)."""
    await synchronize_replies(db, owner, now=now)
    rows = (
        await db.scalars(
            select(ConversationMessage)
            .join(
                DiscussionOpeningRecord,
                DiscussionOpeningRecord.id.cast(String)
                == ConversationMessage.message_metadata[REPLY_TO].astext,
            )
            .where(
                DiscussionOpeningRecord.user_id == owner,
                ConversationMessage.conversation_id == DiscussionOpeningRecord.conversation_id,
                ConversationMessage.role == "user",
                ConversationMessage.hidden.is_(False),
                ConversationMessage.message_metadata["run_id"].astext == run_id,
            )
            .with_for_update(of=ConversationMessage)
        )
    ).all()
    for reply in rows:
        reply.message_metadata = {**(reply.message_metadata or {}), CONTROLS_APPLIED: True}
    await db.flush()
