"""What proactive notifications met, offered to the habits domain (ADR-375).

The « review your notifications » proposal asks only after many notifications
met no reaction at all. ``heartbeat`` imports habits, so this reader is
installed into ``habits.usage_ports`` at import and again by the boot.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.habits.proposal_rules import ProactiveFeedback
from src.domains.habits.usage_ports import install_proactive_feedback_reader
from src.domains.heartbeat.models import HeartbeatNotification


async def read_proactive_feedback(
    db: AsyncSession, user_id: UUID, since: datetime
) -> ProactiveFeedback:
    """The proactive notifications sent since an instant, and how many got a thumb.

    Args:
        db: The caller's session.
        user_id: The person.
        since: The window's start (UTC).

    Returns:
        The two exact counts.
    """
    sent, reacted = (
        await db.execute(
            select(func.count(), func.count(HeartbeatNotification.user_feedback)).where(
                HeartbeatNotification.user_id == user_id,
                HeartbeatNotification.created_at >= since,
            )
        )
    ).one()
    return ProactiveFeedback(sent=int(sent), reacted=int(reacted))


install_proactive_feedback_reader(read_proactive_feedback)
