"""Shared feedback effects preserve the source audit, presence and archived-card policy."""

from contextlib import suppress
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from src.core.exceptions import ResourceNotFoundError
from src.domains.conversations.repository import ConversationRepository
from src.domains.interests.models import InterestNotification, UserInterest
from src.domains.interests.repository import InterestNotificationRepository, InterestRepository
from src.domains.interests.schemas import InterestFeedbackKind
from src.domains.users.extraction_consent import invalidate_extractions
from src.domains.users.models import User


@dataclass(frozen=True)
class InterestFeedbackEffects:
    messages_updated: int
    audit_updated: bool


def record_interest_feedback_metric(feedback: InterestFeedbackKind) -> None:
    """Metrics follow a confirmed commit and cannot change its outcome."""
    with suppress(Exception):
        from src.infrastructure.observability.metrics_registry import track_proactive_feedback

        track_proactive_feedback(task_type="interest", feedback_type=feedback)


async def get_feedback_notification(
    db: AsyncSession, owner: UUID, identity: UUID, *, lock: bool = False
) -> InterestNotification:
    query = (
        select(InterestNotification)
        .where(InterestNotification.user_id == owner, InterestNotification.id == identity)
        .options(defer(InterestNotification.content_embedding), defer(InterestNotification.content))
        .execution_options(populate_existing=True)
    )
    if lock:
        query = query.with_for_update()
    row = await db.scalar(query)
    if row is None or row.interest_id is None:
        raise ResourceNotFoundError("interest_notification", identity)
    return row


async def apply_interest_feedback_effects(
    db: AsyncSession,
    actor: User,
    interest: UserInterest,
    feedback: InterestFeedbackKind,
    *,
    run_id: str | None = None,
) -> InterestFeedbackEffects:
    """Caller holds account then interest locks; no helper commits independently."""
    if interest.user_id != actor.id:
        raise ResourceNotFoundError("interest", interest.id)
    invalidate_extractions(actor)
    await InterestRepository(db).apply_feedback(interest, feedback)
    from src.domains.habits.presence import record_presence

    await record_presence(db, actor, kind="feedback")
    audited = False
    if run_id:
        audited = await InterestNotificationRepository(db).update_feedback_by_run_id(
            run_id=run_id,
            user_id=actor.id,
            interest_id=interest.id,
            feedback=feedback,
        )
    messages = await ConversationRepository(db).mark_proactive_feedback_submitted(
        user_id=actor.id,
        target_id=interest.id,
        feedback_value=feedback,
        run_id=run_id,
    )
    await db.flush()
    return InterestFeedbackEffects(messages_updated=messages, audit_updated=audited)
