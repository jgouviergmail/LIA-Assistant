"""Last human-activity probe for the proactive eligibility gate (lot 1, D-01).

The "don't interrupt an active user" gate needs one fact: when did this user
last send a REAL message? The historical implementation read a phantom
attribute and a nonexistent model, so the gate never fired (executed proof
2026-08-19). This module is the single authoritative answer, reusing the
human-activity semantics of the habits aggregation: user-role rows only, the
``is_automated_source`` marker excluded (scheduled actions and heartbeat
inject user-role messages that are machine work, not presence).

Lives in its own module: ``conversations/repository.py`` sits one file-size
ratchet away from its frozen cap (same reason as ``response_feedback.py``).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.field_names import FIELD_IS_AUTOMATED_SOURCE
from src.domains.conversations.models import Conversation, ConversationMessage


async def fetch_last_user_activity_at(
    user_id: UUID,
    db: AsyncSession,
    since: datetime,
) -> datetime | None:
    """Timestamp of the user's most recent human message since ``since``.

    The ``since`` floor bounds the scan to the cooldown horizon (minutes):
    the per-conversation ``(conversation_id, created_at)`` index makes this a
    tail probe, never a history walk.

    Args:
        user_id: Owner.
        db: Caller-owned session (the proactive runner's).
        since: Lower bound — activity older than this is irrelevant to the
            cooldown decision.

    Returns:
        The latest matching ``created_at``, or None when the user sent no
        human message inside the horizon.
    """
    stmt = (
        select(func.max(ConversationMessage.created_at))
        .join(Conversation, ConversationMessage.conversation_id == Conversation.id)
        .where(
            Conversation.user_id == user_id,
            ConversationMessage.role == "user",
            ConversationMessage.created_at >= since,
            ConversationMessage.message_metadata[FIELD_IS_AUTOMATED_SOURCE].astext.is_distinct_from(
                "true"
            ),
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
