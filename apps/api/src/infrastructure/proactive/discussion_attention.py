"""Personal initiatives yield to human turns, pending approval and existing alerts."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.utils import HITLStore
from src.domains.conversations.activity_probe import fetch_last_user_activity_at
from src.domains.conversations.repository import ConversationRepository
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.heartbeat.models import HeartbeatNotification
from src.domains.interests.models import InterestNotification
from src.domains.proactive_discussions.models import DiscussionOpeningRecord
from src.domains.proactive_discussions.repository import DiscussionRepository
from src.domains.proactive_discussions.run_types import RunClaim, StopReason
from src.domains.reminders.models import Reminder
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database.session import get_db_context
from src.infrastructure.proactive.discussion_control import load_controls
from src.infrastructure.streaming.run_stream_broker import get_active_run


class InitiativeStopped(ValueError):
    """Expected discretionary abstention, without discarding known billing.

    Attributes:
        reason: Why, in the run's closed vocabulary.
    """

    def __init__(self, reason: StopReason) -> None:
        super().__init__(reason)
        self.reason: StopReason = reason


async def attention_available(
    db: AsyncSession, owner: UUID, *, now: datetime, lease_owner: str | None = None
) -> bool:
    """Whether the person's attention is free for a personal initiative now.

    It is not when the person wrote recently, an opening is still pending or came
    recently, a reminder is about to ring, a turn is streaming (other than the run's
    own) or an approval is waiting; a recent proactive notification or interest alert
    also blocks it when the operator sets a gap. Every delay is a setting.

    Args:
        db: The caller's session; committed before the Redis checks.
        owner: The account.
        now: The current instant.
        lease_owner: The stream id that is the run's own, ignored as a busy turn.

    Returns:
        True when nothing claims the person's attention.
    """
    if (
        await fetch_last_user_activity_at(
            owner, db, now - timedelta(minutes=settings.discussion_attention_recent_turn_minutes)
        )
        is not None
    ):
        return False
    pending = await db.scalar(
        select(DiscussionOpeningRecord.id)
        .where(
            DiscussionOpeningRecord.user_id == owner,
            DiscussionOpeningRecord.state == "pending",
            DiscussionOpeningRecord.expires_at > now,
        )
        .limit(1)
    )
    if pending is not None:
        return False
    gaps = (
        (HeartbeatNotification, settings.discussion_attention_alert_gap_minutes),
        (InterestNotification, settings.discussion_attention_alert_gap_minutes),
        (DiscussionOpeningRecord, settings.discussion_attention_opening_gap_minutes),
    )
    for model, minutes in gaps:
        if minutes and (
            await db.scalar(
                select(model.id)
                .where(
                    model.user_id == owner,
                    model.created_at > now - timedelta(minutes=minutes),
                )
                .limit(1)
            )
            is not None
        ):
            return False
    if (
        await db.scalar(
            select(Reminder.id)
            .where(
                Reminder.user_id == owner,
                Reminder.status.in_(("pending", "processing")),
                Reminder.trigger_at
                <= now + timedelta(minutes=settings.discussion_attention_reminder_ahead_minutes),
            )
            .limit(1)
        )
        is not None
    ):
        return False
    conversation = await ConversationRepository(db).get_active_for_user(owner)
    conversation_id = str(conversation.id) if conversation is not None else None
    # Release SQL connections before Redis work: the caller performs only short
    # reads here; no provider or model is entered from this function.
    if conversation_id is not None:
        await db.commit()
        redis = await get_redis_cache()
        active = await get_active_run(redis, conversation_id)
        if active is not None and (lease_owner is None or active.get("stream_id") != lease_owner):
            return False
        if await HITLStore(
            redis_client=redis, ttl_seconds=settings.hitl_pending_data_ttl_seconds
        ).has_interrupt(conversation_id):
            return False
    return True


class DiscussionAuthority:
    """Check again, before every source read and model call, that the run may still act.

    The producer and the operator's switch must be on, the person's attention free
    (a rebuild does not wait for it), the controls unchanged since the run started,
    and the claim renewed.
    """

    def __init__(
        self, claim: RunClaim, directives_revision: str, *, context_only: bool = False
    ) -> None:
        self.claim, self.directives_revision = claim, directives_revision
        self.context_only = context_only

    async def check(self, *, lease_owner: str | None = None) -> None:
        """Raise unless the run may still act now; renew its lease.

        Args:
            lease_owner: The stream id that is the run's own, if any.

        Raises:
            InitiativeStopped: The producer is off, attention is busy, the controls
                changed or the claim was lost.
            DirectiveBudgetExceeded: The controls no longer fit their budget.
        """
        if not settings.proactive_discussions_enabled:
            raise InitiativeStopped("producer_disabled")
        async with get_db_context() as db:
            try:
                await require_capability_fresh(db, PlatformCapability.PROACTIVE_DISCUSSIONS)
            except AuthorizationError as exc:
                raise InitiativeStopped("producer_disabled") from exc
            repo = DiscussionRepository(db)
            if not self.context_only and not await attention_available(
                db, self.claim.owner_id, now=datetime.now(UTC), lease_owner=lease_owner
            ):
                raise InitiativeStopped("attention_busy")
            directives = await load_controls(db, self.claim.owner_id, now=datetime.now(UTC))
            if directives.revision != self.directives_revision:
                raise InitiativeStopped("directives_changed")
            if not await repo.renew_claim(
                self.claim,
                now=datetime.now(UTC),
                lease_seconds=settings.discussion_run_lease_seconds,
            ):
                raise InitiativeStopped("stale_claim")
