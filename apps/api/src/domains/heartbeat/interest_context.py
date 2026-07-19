"""Interest context source for the heartbeat decision (ADR-135).

Extracted from `context_aggregator.py`: building the interest sample now
carries real logic (subject grouping, unified-ledger serving counts) that
belongs in its own unit rather than inflating the aggregator.

The sample is deliberately VARIED rather than top-weighted: the decision LLM
can only mention interests it is shown, so rotating the sample is what breaks
the day-after-day anchoring on a single dominant topic.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings


async def fetch_varied_interest_topics(
    db: AsyncSession,
    user_id: UUID,
) -> list[dict[str, str]] | None:
    """Build a subject-diverse sample of the user's active interest topics.

    Serving counts come from the unified ledger (interest-flow rows AND
    heartbeat mention rows), so a topic covered by either flow steps aside.

    Args:
        db: Database session (owned by the caller).
        user_id: User UUID.

    Returns:
        List of {topic} dicts for prompt injection, or None when the user has
        no active interest.
    """
    from src.domains.interests.repository import (
        InterestNotificationRepository,
        InterestRepository,
    )
    from src.domains.interests.selection import pick_varied_sample

    settings = get_settings()
    actives = await InterestRepository(db).get_active_for_user(user_id)
    if not actives:
        return None

    recent = await InterestNotificationRepository(db).get_recent_for_user(
        user_id=user_id,
        days=settings.heartbeat_recent_window_days,
    )
    sample = pick_varied_sample(
        candidates=actives,
        subject_by_interest={i.id: i.subject for i in actives},
        recent_notifications=[(n.interest_id, n.created_at) for n in recent],
        now=datetime.now(UTC),
        sample_size=settings.heartbeat_interest_sample_size,
        lookback_days=settings.heartbeat_recent_window_days,
    )
    if not sample:
        return None
    return [{"topic": interest.topic} for interest in sample]
