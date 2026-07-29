"""Repository for PhoneCall rows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.telephony.models import (
    NotificationStatus,
    PhoneCall,
    PhoneCallOutcome,
    PhoneCallStatus,
    ReturnSynthesisStatus,
)

# Statuses that count as an in-flight call (mirrors the model's partial-index predicate).
_ACTIVE_STATUSES = (PhoneCallStatus.DIALING, PhoneCallStatus.IN_PROGRESS)


class TelephonyRepository(BaseRepository[PhoneCall]):
    """Data access for ``PhoneCall``.

    Uses explicit queries (no reliance on the base soft-delete filter — PhoneCall
    has no ``is_active`` column). Row creation goes through the inherited
    ``create()`` (flush + refresh), which raises ``IntegrityError`` on the
    one-active-call-per-user partial unique index (F12).
    """

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, PhoneCall)

    async def get_by_call_id(self, call_id: UUID) -> PhoneCall | None:
        """Fetch a call by its id (our ``call_id`` reconciliation key)."""
        return await self.db.get(PhoneCall, call_id)

    async def get_active_for_user(self, user_id: UUID) -> PhoneCall | None:
        """Return the user's in-flight call (dialing/in_progress), if any."""
        stmt = select(PhoneCall).where(
            PhoneCall.user_id == user_id,
            PhoneCall.status.in_(_ACTIVE_STATUSES),
        )
        return (await self.db.scalars(stmt)).first()

    async def list_recent_for_user(self, user_id: UUID, limit: int = 20) -> list[PhoneCall]:
        """Return the user's most recent calls (newest first) for the calls surface."""
        stmt = (
            select(PhoneCall)
            .where(PhoneCall.user_id == user_id)
            .order_by(PhoneCall.created_at.desc())
            .limit(limit)
        )
        return list((await self.db.scalars(stmt)).all())

    async def get_by_elevenlabs_conversation_id(self, conversation_id: str) -> PhoneCall | None:
        """Reconciliation fallback: match on the ElevenLabs conversation id."""
        stmt = select(PhoneCall).where(PhoneCall.elevenlabs_conversation_id == conversation_id)
        return (await self.db.scalars(stmt)).first()

    async def mark_completed(
        self,
        call_id: UUID,
        *,
        status: PhoneCallStatus,
        call_seconds: Decimal | None,
        summary: str,
        structured_data: dict[str, Any],
        debrief: dict[str, Any] | None,
        outcome: PhoneCallOutcome | None,
        completed_at: datetime,
        notification_content: str,
        notification_title: str,
    ) -> bool:
        """Atomically transition an in-flight call to terminal + arm the return.

        Server-side conditional UPDATE guarded on the active statuses so a
        duplicated post-call webhook processes the call exactly once (returns
        ``False`` for the loser). Persists only ``summary`` + ``structured_data``
        — the raw transcript is never stored (D-8).

        T1 durability: in the SAME atomic transition it writes ``notification_status
        = PENDING`` and the minimal ``notification_payload`` (content + title). The
        return is therefore committed as an outbox record BEFORE it is dispatched,
        so a crash between the commit and the dispatch cannot lose it — the
        notification reaper re-dispatches it from the payload without re-synthesizing.

        Returns:
            ``True`` if this call transitioned the row (winner), ``False`` if the
            row was already terminal (already processed / lost the race).
        """
        stmt = (
            update(PhoneCall)
            .where(PhoneCall.id == call_id, PhoneCall.status.in_(_ACTIVE_STATUSES))
            .values(
                status=status,
                call_seconds=call_seconds,
                summary=summary,
                structured_data=structured_data,
                debrief=debrief,
                outcome=outcome,
                completed_at=completed_at,
                notification_status=NotificationStatus.PENDING,
                notification_payload={"content": notification_content, "title": notification_title},
                notification_attempts=0,
                # T1 approach A: synthesis is done — close the pre-synthesis inbox and
                # PURGE the encrypted transcript (it only rested for the synthesis window).
                return_status=ReturnSynthesisStatus.SYNTHESIZED,
                return_webhook_encrypted=None,
            )
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def persist_return_inbox(
        self, call_id: UUID, *, encrypted_payload: str, received_at: datetime
    ) -> None:
        """Durably record the post-call webhook BEFORE synthesis (T1 approach A).

        Called from the webhook handler and committed BEFORE the 200 response, so a
        crash during the fire-and-forget synthesis leaves a recoverable ``RECEIVED``
        inbox row (with the Fernet-encrypted payload) that the return reaper replays.

        Idempotent: a duplicated webhook re-persists ``RECEIVED``; it never reverts a
        row already ``SYNTHESIZED`` (done) or ``FAILED`` (gave up) back to the inbox.
        ``is_distinct_from`` keeps the very first webhook (``return_status IS NULL``)
        eligible, unlike a bare ``NOT IN`` which NULL would exclude.
        """
        await self.db.execute(
            update(PhoneCall)
            .where(
                PhoneCall.id == call_id,
                PhoneCall.return_status.is_distinct_from(ReturnSynthesisStatus.SYNTHESIZED),
                PhoneCall.return_status.is_distinct_from(ReturnSynthesisStatus.FAILED),
            )
            .values(
                return_status=ReturnSynthesisStatus.RECEIVED,
                return_webhook_encrypted=encrypted_payload,
                return_received_at=received_at,
            )
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()

    async def fetch_recoverable_returns(
        self, *, grace_cutoff: datetime, max_age_cutoff: datetime, limit: int
    ) -> list[PhoneCall]:
        """RECEIVED inbox rows a crash stranded before synthesis, oldest first.

        Bounded to ``[max_age_cutoff, grace_cutoff)``: newer than the grace window is
        skipped (the live fire-and-forget synthesis is not raced), older than
        max-age is left for :meth:`expire_stale_returns` to retire. No row lock —
        single-instance reaper (leader election + ``max_instances=1``).
        """
        stmt = (
            select(PhoneCall)
            .where(
                PhoneCall.return_status == ReturnSynthesisStatus.RECEIVED,
                PhoneCall.return_received_at < grace_cutoff,
                PhoneCall.return_received_at >= max_age_cutoff,
            )
            .order_by(PhoneCall.return_received_at.asc())
            .limit(limit)
        )
        return list((await self.db.scalars(stmt)).all())

    async def expire_stale_returns(self, *, max_age_cutoff: datetime) -> int:
        """Give up on inbox rows whose synthesis never completed within max-age.

        Retires ``RECEIVED`` → ``FAILED``, marks the call FAILED and PURGES the
        encrypted transcript (D-8). Returns the number of rows retired.
        """
        stmt = (
            update(PhoneCall)
            .where(
                PhoneCall.return_status == ReturnSynthesisStatus.RECEIVED,
                PhoneCall.return_received_at < max_age_cutoff,
            )
            .values(
                return_status=ReturnSynthesisStatus.FAILED,
                return_webhook_encrypted=None,
                status=PhoneCallStatus.FAILED,
                error="return_synthesis_gave_up",
            )
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return int(result.rowcount)  # type: ignore[attr-defined]

    async def mark_notification_delivered(self, call_id: UUID) -> None:
        """Flip a PENDING return notification to DELIVERED after a successful dispatch.

        Idempotent conditional UPDATE (only PENDING → DELIVERED): a duplicate call,
        or a reaper racing the live dispatch, is a harmless no-op.
        """
        await self.db.execute(
            update(PhoneCall)
            .where(
                PhoneCall.id == call_id,
                PhoneCall.notification_status == NotificationStatus.PENDING,
            )
            .values(notification_status=NotificationStatus.DELIVERED)
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()

    async def fetch_recoverable_notifications(
        self, *, cutoff: datetime, max_attempts: int, limit: int
    ) -> list[PhoneCall]:
        """PENDING return notifications a crash left undelivered, oldest first.

        Only rows completed before ``cutoff`` (past the grace window, so the live
        in-process dispatch is not raced) and still under the attempt cap. No row
        lock is taken: the reaper runs single-instance (scheduler leader election +
        ``max_instances=1``), which is the concurrency lease — and the dispatcher
        commits mid-batch, which would release a ``FOR UPDATE`` lock anyway.
        """
        stmt = (
            select(PhoneCall)
            .where(
                PhoneCall.notification_status == NotificationStatus.PENDING,
                PhoneCall.completed_at < cutoff,
                PhoneCall.notification_attempts < max_attempts,
            )
            .order_by(PhoneCall.completed_at.asc())
            .limit(limit)
        )
        return list((await self.db.scalars(stmt)).all())

    async def record_notification_failure(self, call_id: UUID, *, max_attempts: int) -> None:
        """Count a failed re-dispatch; mark FAILED once the attempt cap is reached.

        Atomic column arithmetic (never SELECT-then-write), split into two guarded
        UPDATEs so each enum assignment goes through the column's ``native_enum=False``
        coercion (which stores the member NAME) — a ``case()`` over ``str``-enum
        members would instead bind the lowercase *value* and corrupt the column.
        """
        # 1. Count the failed attempt (only while still PENDING — a delivered/failed
        #    row is never touched).
        await self.db.execute(
            update(PhoneCall)
            .where(
                PhoneCall.id == call_id,
                PhoneCall.notification_status == NotificationStatus.PENDING,
            )
            .values(notification_attempts=PhoneCall.notification_attempts + 1)
            .execution_options(synchronize_session=False)
        )
        # 2. Retire to FAILED once the (now-incremented) attempts reach the cap, so a
        #    permanently-failing dispatch stops being retried instead of looping.
        await self.db.execute(
            update(PhoneCall)
            .where(
                PhoneCall.id == call_id,
                PhoneCall.notification_status == NotificationStatus.PENDING,
                PhoneCall.notification_attempts >= max_attempts,
            )
            .values(notification_status=NotificationStatus.FAILED)
            .execution_options(synchronize_session=False)
        )
        await self.db.commit()

    async def set_conversation_id(self, call_id: UUID, conversation_id: str | None) -> None:
        """Persist the ElevenLabs conversation id after a successful dial (short tx)."""
        await self.db.execute(
            update(PhoneCall)
            .where(PhoneCall.id == call_id)
            .values(elevenlabs_conversation_id=conversation_id)
        )
        await self.db.commit()

    async def mark_dial_failed(self, call_id: UUID, error: str) -> None:
        """Transition a just-created dialing row to failed when the vendor call errors."""
        await self.db.execute(
            update(PhoneCall)
            .where(PhoneCall.id == call_id)
            .values(status=PhoneCallStatus.FAILED, error=error)
        )
        await self.db.commit()

    async def close_zombie(self, call_id: UUID, error: str) -> bool:
        """Close ONE zombie active row inline (self-healing one-active guard).

        Same transition and exclusions as ``recover_stale`` but targeted by PK
        and without a time cutoff — the caller decides eligibility (vendor says
        the conversation ended, or the stale threshold elapsed). ``RECEIVED``
        rows stay untouched: their webhook DID arrive and the return reaper owns
        them (the call is over but its return is in flight — the guard keeps
        refusing until ``mark_completed`` lands, seconds away). Returns True
        when the row was actually transitioned (atomic conditional UPDATE).
        """
        stmt = (
            update(PhoneCall)
            .where(
                PhoneCall.id == call_id,
                PhoneCall.status.in_(_ACTIVE_STATUSES),
                PhoneCall.return_status.is_distinct_from(ReturnSynthesisStatus.RECEIVED),
            )
            .values(status=PhoneCallStatus.FAILED, error=error)
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        count: int = result.rowcount  # type: ignore[attr-defined]
        return count > 0

    async def recover_stale(self, timeout_minutes: int) -> int:
        """Mark in-flight calls with no terminal webhook as failed (crash recovery).

        Returns the number of rows transitioned. Server-side UPDATE — no
        SELECT-then-write race.
        """
        cutoff = datetime.now(UTC) - timedelta(minutes=timeout_minutes)
        stmt = (
            update(PhoneCall)
            .where(
                PhoneCall.status.in_(_ACTIVE_STATUSES),
                PhoneCall.created_at < cutoff,
                # T1 approach A: a call whose webhook DID arrive but whose synthesis
                # crashed carries a RECEIVED inbox row — the return reaper owns its
                # recovery; never fail it out from under that path (is_distinct_from
                # keeps ordinary no-webhook calls, whose return_status IS NULL, eligible).
                PhoneCall.return_status.is_distinct_from(ReturnSynthesisStatus.RECEIVED),
            )
            .values(status=PhoneCallStatus.FAILED, error="stale_no_webhook")
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        count: int = result.rowcount  # type: ignore[attr-defined]
        return count

    async def purge_expired(self) -> int:
        """Purge summary/structured_data/debrief past their retention TTL (D-8).

        The row is kept (audit) but the content fields are cleared. Returns the
        number of rows purged.
        """
        now = datetime.now(UTC)
        stmt = (
            update(PhoneCall)
            .where(
                PhoneCall.expires_at.is_not(None),
                PhoneCall.expires_at < now,
                PhoneCall.summary.is_not(None),
            )
            .values(summary=None, structured_data={}, debrief=None)
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        count: int = result.rowcount  # type: ignore[attr-defined]
        return count
