"""One short transaction admits, fences or settles cross-worker voice work."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import CONVERSATION_OWNER_LOCK_SCOPE
from src.core.conversation_execution import (
    ExecutionKind,
    ExecutionPhase,
    ExecutionRevoked,
    ReservationPurpose,
    ReservationWorkPhase,
    ReservedWork,
    RunAdmission,
)
from src.core.repository import BaseRepository
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.conversations.execution_models import ConversationExecution
from src.domains.conversations.execution_repository import _admission, _owned
from src.domains.conversations.reservation_models import ConversationReservationWork
from src.domains.users.conversation_authority import hold_conversation_source
from src.infrastructure.database.owner_lock import hold_owner_lock


class ConversationReservationRepository(BaseRepository[ConversationReservationWork]):
    """Flush only; no caller may hold these locks across a network operation."""

    def __init__(self, db: AsyncSession) -> None:
        """Use the caller's short session for both work and reservation transitions."""
        super().__init__(db, ConversationReservationWork)

    async def load(self, owner_id: UUID, activity_id: UUID | None, session_id: str) -> RunAdmission:
        """Recover private authority from the server-owned record, never from a client token."""
        statement = select(ConversationExecution)
        if activity_id is not None:
            statement = statement.where(ConversationExecution.id == activity_id)
        row = await self.db.scalar(
            statement.where(
                ConversationExecution.user_id == owner_id,
                ConversationExecution.stream_id == session_id,
                ConversationExecution.kind == ExecutionKind.LIVE,
                ConversationExecution.phase.in_((ExecutionPhase.RUNNING, ExecutionPhase.DRAINING)),
            ).execution_options(populate_existing=True)
        )
        if row is None:
            raise ExecutionRevoked()
        return _admission(row)

    async def is_closed(self, admission: RunAdmission) -> bool:
        """Read the exact reservation's explicit close, never infer it from a missing cache."""
        phase = await self.db.scalar(select(ConversationExecution.phase).where(*_owned(admission)))
        return phase == ExecutionPhase.CLOSED

    async def is_closed_session(self, owner: UUID, activity: UUID, session_id: str) -> bool:
        """Check a server-owned Redis binding before removing only that record's token."""
        return bool(
            await self.db.scalar(
                select(
                    exists().where(
                        ConversationExecution.user_id == owner,
                        ConversationExecution.id == activity,
                        ConversationExecution.stream_id == session_id,
                        ConversationExecution.kind == ExecutionKind.LIVE,
                        ConversationExecution.phase == ExecutionPhase.CLOSED,
                    )
                )
            )
        )

    async def active_admission(self, owner_id: UUID) -> RunAdmission | None:
        """Read the owner's private voice reservation for cache reconciliation only."""
        row = await self.db.scalar(
            select(ConversationExecution)
            .where(
                ConversationExecution.user_id == owner_id,
                ConversationExecution.kind == ExecutionKind.LIVE,
                ConversationExecution.phase != ExecutionPhase.CLOSED,
            )
            .execution_options(populate_existing=True)
        )
        return _admission(row) if row is not None else None

    async def _parent(
        self, admission: RunAdmission, *, require_source: bool = True
    ) -> ConversationExecution:
        """Serialize child admission and the final close in the common lock order."""
        if admission.kind != ExecutionKind.LIVE:
            raise ExecutionRevoked()
        await hold_owner_lock(self.db, CONVERSATION_OWNER_LOCK_SCOPE, admission.target.owner_id)
        if require_source:
            await hold_conversation_source(self.db, admission.target.owner_id, admission.target)
        row = await self.db.scalar(
            select(ConversationExecution)
            .where(*_owned(admission))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise ExecutionRevoked()
        return row

    async def _new(
        self, admission: RunAdmission, worker_id: UUID, purpose: ReservationPurpose
    ) -> ReservedWork:
        """Create a uniquely owned contribution while the parent is locked."""
        row = ConversationReservationWork(
            activity_id=admission.activity_id, worker_id=worker_id, purpose=purpose
        )
        self.db.add(row)
        await self.db.flush()
        return ReservedWork(admission, row.id, row.worker_id, row.owner_token, row.purpose)

    async def begin(
        self, admission: RunAdmission, *, worker_id: UUID, purpose: ReservationPurpose
    ) -> ReservedWork:
        """Admit work only while the session still accepts new requests."""
        parent = await self._parent(admission)
        if parent.phase != ExecutionPhase.RUNNING:
            raise ExecutionRevoked()
        return await self._new(admission, worker_id, purpose)

    async def require_open(self, admission: RunAdmission) -> None:
        """Validate a delegation before the graph claims its own independent slot."""
        parent = await self._parent(admission)
        if parent.phase != ExecutionPhase.RUNNING:
            raise ExecutionRevoked()

    async def begin_closing(self, admission: RunAdmission, *, worker_id: UUID) -> ReservedWork:
        """Claim one closing and stop new requests before any closing effect begins."""
        parent = await self._parent(admission)
        if parent.phase != ExecutionPhase.RUNNING:
            raise ExecutionRevoked()
        opening = await self.db.scalar(
            select(
                exists().where(
                    ConversationReservationWork.activity_id == parent.id,
                    ConversationReservationWork.purpose == "opening",
                    ConversationReservationWork.phase != ReservationWorkPhase.CLOSED,
                )
            )
        )
        if opening:
            raise ExecutionRevoked()
        parent.phase = ExecutionPhase.DRAINING
        return await self._new(admission, worker_id, "closing")

    async def _work(
        self, work: ReservedWork, *, include_unknown: bool = False
    ) -> ConversationReservationWork | None:
        """A stale token, another worker or an already closed task authorizes nothing."""
        row = ConversationReservationWork
        result = await self.db.execute(
            select(ConversationReservationWork)
            .where(
                row.id == work.id,
                row.activity_id == work.admission.activity_id,
                row.worker_id == work.worker_id,
                row.owner_token == work.owner_token,
                row.purpose == work.purpose,
                row.phase.in_(
                    (ReservationWorkPhase.RUNNING, ReservationWorkPhase.UNKNOWN)
                    if include_unknown
                    else (ReservationWorkPhase.RUNNING,)
                ),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def require_current(self, work: ReservedWork) -> None:
        """Hold the generation and exact live child through a short publication transaction."""
        await self._require_current_work(work)

    async def _require_current_work(self, work: ReservedWork) -> ConversationReservationWork:
        """Return the owned work row under the same authority as publication."""
        parent = await self._parent(work.admission)
        if parent.phase not in (ExecutionPhase.RUNNING, ExecutionPhase.DRAINING):
            raise ExecutionRevoked()
        row = await self._work(work)
        if row is None:
            raise ExecutionRevoked()
        return row

    async def record_standby_result(self, work: ReservedWork, recap: str | None) -> bool:
        """Accept a relay result once, holding its session through card publication."""
        if work.purpose != "relay":
            raise ExecutionRevoked()
        row = await self._require_current_work(work)
        if row.standby_relay_settled:
            return False
        row.standby_relay_settled = True
        row.standby_recap = encrypt_data(recap) if recap else None
        await self.db.flush()
        return True

    async def take_standby_recaps(self, work: ReservedWork) -> list[str]:
        """Consume only this reservation's pending recaps in the card's transaction."""
        await self.require_current(work)
        row = ConversationReservationWork
        pending = await self.db.scalars(
            select(row)
            .where(row.activity_id == work.admission.activity_id, row.standby_recap.is_not(None))
            .order_by(row.created_at, row.id)
        )
        recaps: list[str] = []
        for entry in pending:
            if entry.standby_recap is not None:
                recaps.append(decrypt_data(entry.standby_recap))
                entry.standby_recap = None
        return recaps

    async def _close(self, parent: ConversationExecution, now: datetime) -> None:
        """Retire any temporary recap when no closing can publish it any more."""
        row = ConversationReservationWork
        await self.db.execute(
            update(row)
            .where(row.activity_id == parent.id, row.standby_recap.is_not(None))
            .values(standby_recap=None)
        )
        parent.phase, parent.closed_at = ExecutionPhase.CLOSED, now

    async def fork(
        self, work: ReservedWork, *, worker_id: UUID, purpose: ReservationPurpose
    ) -> ReservedWork:
        """Commit the final relay before its parent may settle, even during closing."""
        await self.require_current(work)
        return await self._new(work.admission, worker_id, purpose)

    async def finish(self, work: ReservedWork) -> bool:
        """Acknowledge one joined task; only the last closing child releases the target."""
        parent = await self._parent(work.admission, require_source=False)
        if parent.phase not in (
            ExecutionPhase.RUNNING,
            ExecutionPhase.DRAINING,
            ExecutionPhase.RECOVERING,
        ):
            return False
        row = await self._work(work)
        if row is None:
            return False
        row.phase = ReservationWorkPhase.CLOSED
        row.closed_at = datetime.now(UTC)
        await self.db.flush()
        outstanding = await self.db.scalar(
            select(
                exists().where(
                    ConversationReservationWork.activity_id == parent.id,
                    ConversationReservationWork.phase != ReservationWorkPhase.CLOSED,
                )
            )
        )
        if parent.phase == ExecutionPhase.DRAINING and not outstanding:
            await self._close(parent, datetime.now(UTC))
        await self.db.flush()
        return True

    async def abandon_unstarted(self, work: ReservedWork) -> None:
        """Compensate a joined admission whose body never started.

        A lost commit acknowledgment may have rolled the entire admission back.
        A closing that never started must reopen the existing session rather
        than discard its transcript. Unknown provider work is never released.
        """
        try:
            parent = await self._parent(work.admission, require_source=False)
        except ExecutionRevoked:
            return
        if await self._work(work) is None:
            return
        if work.purpose == "closing" and parent.phase == ExecutionPhase.DRAINING:
            parent.phase = ExecutionPhase.RUNNING
        elif work.purpose == "opening" and parent.phase == ExecutionPhase.RUNNING:
            parent.phase = ExecutionPhase.DRAINING
        await self.db.flush()
        await self.finish(work)

    async def close_failed_opening(self, work: ReservedWork) -> None:
        """Release a known failed start, retaining any quarantined provider outcome."""
        if work.purpose != "opening":
            raise ValueError("Only an opening contribution may close a failed start")
        await self.abandon_unstarted(work)

    async def mark_unknown(self, work: ReservedWork) -> None:
        """An unacknowledged provider act stays quarantined; it is never silently retried."""
        parent = await self._parent(work.admission, require_source=False)
        row = await self._work(work, include_unknown=True)
        if (
            row is not None
            and row.phase == ReservationWorkPhase.UNKNOWN
            and parent.phase == ExecutionPhase.RECOVERING
        ):
            return
        if row is None or parent.phase not in (
            ExecutionPhase.RUNNING,
            ExecutionPhase.DRAINING,
            ExecutionPhase.RECOVERING,
        ):
            raise ExecutionRevoked()
        row.phase = ReservationWorkPhase.UNKNOWN
        parent.phase = ExecutionPhase.RECOVERING
        await self.db.flush()

    async def retire_idle(self, admission: RunAdmission) -> bool:
        """Revoke a missing browser's slot only when SQL proves there is no actual work.

        The caller first establishes a missing Redis record or an inactive
        account. Neither fact proves a worker ended: the complete child table
        must be empty of unfinished contributions under the same parent lock.
        """
        parent = await self._parent(admission, require_source=False)
        if parent.phase == ExecutionPhase.CLOSED:
            return True
        if parent.phase == ExecutionPhase.RECOVERING:
            return False
        outstanding = await self.db.scalar(
            select(
                exists().where(
                    ConversationReservationWork.activity_id == parent.id,
                    ConversationReservationWork.phase != ReservationWorkPhase.CLOSED,
                )
            )
        )
        if outstanding:
            return False
        await self._close(parent, datetime.now(UTC))
        await self.db.flush()
        return True

    async def quarantine(self, admission: RunAdmission) -> None:
        """An operator withdraws new work without claiming that any worker has stopped."""
        parent = await self._parent(admission, require_source=False)
        if parent.phase != ExecutionPhase.CLOSED:
            parent.phase = ExecutionPhase.RECOVERING
            await self.db.flush()

    async def outstanding_workers(self, admission: RunAdmission) -> frozenset[UUID]:
        """Name every actual unjoined worker, not just the session's original boot."""
        return frozenset(
            await self.db.scalars(
                select(ConversationReservationWork.worker_id).where(
                    ConversationReservationWork.activity_id == admission.activity_id,
                    ConversationReservationWork.phase != ReservationWorkPhase.CLOSED,
                )
            )
        )

    async def close_stopped(self, admission: RunAdmission, *, stopped_workers: set[UUID]) -> bool:
        """Close only a quarantined reservation whose every remaining worker was attested stopped."""
        parent = await self._parent(admission, require_source=False)
        if parent.phase == ExecutionPhase.CLOSED:
            return False
        if parent.phase != ExecutionPhase.RECOVERING:
            raise ValueError("Quarantine the Live reservation before recovery")
        outstanding = list(
            await self.db.scalars(
                select(ConversationReservationWork)
                .where(
                    ConversationReservationWork.activity_id == parent.id,
                    ConversationReservationWork.phase != ReservationWorkPhase.CLOSED,
                )
                .with_for_update()
            )
        )
        if not {row.worker_id for row in outstanding}.issubset(stopped_workers):
            raise ValueError("Every outstanding worker boot must be confirmed stopped")
        now = datetime.now(UTC)
        for row in outstanding:
            row.phase, row.closed_at = ReservationWorkPhase.CLOSED, now
        await self._close(parent, now)
        await self.db.flush()
        return True
