"""A signed call reaches a routine: the door's decision, one step per concern (ADR-386).

Nothing is held across a wait (ADR-304): the routine is READ by its address and
the read ends before the call window in Redis is asked; the WRITE then takes the
routine's row lock for the duplicate check, the backlog bound, the insert and the
arming, and commits at once. A call is answered only once it is durable.

The steps, in the order a refusal costs least:

1. no webhook routine at this address, or a paused one: ``UNKNOWN`` (404) — the
   same answer whichever, so an address tells a stranger nothing;
2. no valid signature under the routine's secret: ``BAD_SIGNATURE``;
3. past the address's own call window: ``RATE_LIMITED``;
4. a delivery id this routine already accepted: ``DUPLICATE`` (answered as
   accepted — the sender's retry is not a second call);
5. as many calls waiting as a routine may keep: ``FULL``;
6. otherwise the call is stored, and wakes the routine for the next pass when it
   sleeps — an instant already armed stands, a failed run's back-off included.

A call a routine was found for is logged once, by its facts (ADR-317): the
routine's id, what the call became, its size — never its body, its address or
its sender's words.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import Enum
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import ROUTINE_WEBHOOK_RATE_LIMIT_KEY_PREFIX
from src.core.security.utils import decrypt_data
from src.domains.scheduled_actions.models import ScheduledAction, TriggerKind
from src.domains.scheduled_actions.webhook_repository import RoutineWebhookRepository
from src.domains.scheduled_actions.webhooks import (
    declared_media_type,
    delivery_id_of,
    presented_signature,
    signature_matches,
)
from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter

logger = structlog.get_logger(__name__)

#: The width of an address's call window, in seconds.
CALL_WINDOW_SECONDS = 60


class CallOutcome(str, Enum):
    """What one call to a routine's address became."""

    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    UNKNOWN = "unknown"
    BAD_SIGNATURE = "bad_signature"
    RATE_LIMITED = "rate_limited"
    FULL = "full"
    TOO_LARGE = "too_large"


def _answers(routine: ScheduledAction | None) -> bool:
    """Whether a routine at this address takes calls: a webhook routine not paused."""
    return (
        routine is not None
        and routine.trigger_kind == TriggerKind.WEBHOOK.value
        and routine.is_enabled
    )


def _secret_of(routine: ScheduledAction) -> str | None:
    """The routine's secret in clear, or None when the stored one cannot be read."""
    if routine.webhook_secret is None:
        return None
    try:
        return decrypt_data(routine.webhook_secret)
    except ValueError:
        # Only a rotated encryption key does this: no signature can ever match
        # until the owner draws a new secret. Said by its facts, never its text.
        logger.error("routine_webhook_secret_unreadable", action_id=str(routine.id))
        return None


async def _within_window(action_id: UUID) -> bool:
    """Count the call in the address's window; True while the window allows it.

    Fails open, like every throttle of ours (ADR-254): Redis being unreachable
    is never why a signed call is refused.
    """
    try:
        limiter = await get_rate_limiter()
        return await limiter.acquire(
            key=f"{ROUTINE_WEBHOOK_RATE_LIMIT_KEY_PREFIX}:{action_id}",
            max_calls=settings.routine_webhook_rate_per_minute,
            window_seconds=CALL_WINDOW_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 — fail open by design
        logger.warning(
            "routine_webhook_window_unavailable",
            action_id=str(action_id),
            error_type=type(exc).__name__,
        )
        return True


class RoutineWebhookService:
    """The door of a routine's address: from a call to a stored delivery."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repository = RoutineWebhookRepository(db)

    async def receive(
        self, key: str, *, body: bytes, headers: Mapping[str, str], at: datetime
    ) -> CallOutcome:
        """Decide what one call becomes, storing it when it is accepted.

        Args:
            key: The address key from the path.
            body: The raw body, already bounded by the caller.
            headers: The request's headers, with lowercase names.
            at: When the call arrived (UTC).

        Returns:
            The outcome; a stored call is committed before this returns.
        """
        routine = await self.repository.find_by_key(key)
        # Everything the door needs is read BEFORE the read ends: a rollback
        # expires the row, and touching it afterwards would reload it.
        action_id = routine.id if routine is not None and _answers(routine) else None
        secret = _secret_of(routine) if routine is not None and action_id is not None else None
        # The read is over: nothing is held while Redis answers (ADR-304).
        await self.db.rollback()
        if action_id is None:
            return CallOutcome.UNKNOWN
        outcome = await self._decide(action_id, key, secret, body=body, headers=headers, at=at)
        logger.info(
            "routine_webhook_call",
            action_id=str(action_id),
            outcome=outcome.value,
            body_bytes=len(body),
        )
        return outcome

    async def _decide(
        self,
        action_id: UUID,
        key: str,
        secret: str | None,
        *,
        body: bytes,
        headers: Mapping[str, str],
        at: datetime,
    ) -> CallOutcome:
        """For a routine found at this address: the signature, the window, the write."""
        if secret is None or not signature_matches(secret, body, presented_signature(headers)):
            return CallOutcome.BAD_SIGNATURE
        if not await _within_window(action_id):
            return CallOutcome.RATE_LIMITED
        return await self._store(action_id, key, body=body, headers=headers, at=at)

    async def _store(
        self,
        action_id: UUID,
        key: str,
        *,
        body: bytes,
        headers: Mapping[str, str],
        at: datetime,
    ) -> CallOutcome:
        """Under the routine's lock: dedup, bound, store, arm, commit."""
        routine = await self.repository.lock_routine(action_id)
        # Paused, switched to another clock or deleted since the read: the
        # address no longer answers.
        if routine is None or not _answers(routine) or routine.webhook_key != key:
            await self.db.rollback()
            return CallOutcome.UNKNOWN
        delivery_id = delivery_id_of(headers)
        if delivery_id is not None and await self.repository.already_received(
            action_id, delivery_id
        ):
            await self.db.rollback()
            return CallOutcome.DUPLICATE
        if await self.repository.count_pending(action_id) >= settings.routine_webhook_max_pending:
            await self.db.rollback()
            return CallOutcome.FULL
        stored = await self.repository.store(
            action_id,
            delivery_id=delivery_id,
            content_type=declared_media_type(headers),
            body=body,
            at=at,
        )
        if stored and routine.next_trigger_at is None:
            # A sleeping routine is woken for the next pass. An instant already
            # armed stands: a pass already due serves this call too, and the
            # back-off of a failed run is not cut short by a sender that keeps
            # calling — a model call a minute, and a pause after five (ADR-386 §7).
            routine.next_trigger_at = at
        await self.db.commit()
        return CallOutcome.ACCEPTED if stored else CallOutcome.DUPLICATE


__all__ = ["CALL_WINDOW_SECONDS", "CallOutcome", "RoutineWebhookService"]
