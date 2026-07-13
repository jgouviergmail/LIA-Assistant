"""Repository for PhoneCall rows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.telephony.models import PhoneCall, PhoneCallOutcome, PhoneCallStatus

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
        outcome: PhoneCallOutcome | None,
        completed_at: datetime,
    ) -> bool:
        """Atomically transition an in-flight call to terminal + persist the result.

        Server-side conditional UPDATE guarded on the active statuses so a
        duplicated post-call webhook processes the call exactly once (returns
        ``False`` for the loser). Persists only ``summary`` + ``structured_data``
        — the raw transcript is never stored (D-8).

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
                outcome=outcome,
                completed_at=completed_at,
            )
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return bool(result.rowcount)  # type: ignore[attr-defined]

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
            )
            .values(status=PhoneCallStatus.FAILED, error="stale_no_webhook")
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        count: int = result.rowcount  # type: ignore[attr-defined]
        return count

    async def purge_expired(self) -> int:
        """Purge summary/structured_data past their retention TTL (D-8).

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
            .values(summary=None, structured_data={})
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        count: int = result.rowcount  # type: ignore[attr-defined]
        return count
