"""Short SQL transitions for account-wide graph admission and voice reservations."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.core.constants import CONVERSATION_OWNER_LOCK_SCOPE, CONVERSATION_RUN_ID_MAX_LENGTH
from src.core.conversation_execution import (
    ExecutionKind,
    ExecutionPhase,
    ExecutionRevoked,
    ExecutionSnapshot,
    RunAdmission,
    RunBusy,
    RunEnd,
)
from src.core.conversation_target import ConversationRef
from src.core.repository import BaseRepository
from src.domains.conversations.execution_authority import require_current_execution
from src.domains.conversations.execution_models import (
    ACTIVE_EXECUTION_PREDICATE,
    ConversationExecution,
)
from src.domains.conversations.models import Conversation
from src.domains.users.conversation_authority import hold_conversation_source
from src.infrastructure.database.owner_lock import hold_owner_lock


def _target(row: ConversationExecution) -> ConversationRef:
    """Freeze the original target, without resolving today's conversation again."""
    return ConversationRef(
        row.user_id,
        row.conversation_id,
        row.conversation_kind,
        row.conversation_revision,
        row.runtime_id,
    )


def _admission(row: ConversationExecution) -> RunAdmission:
    """Detach authority before the caller releases its short transaction."""
    return RunAdmission(
        row.id,
        _target(row),
        row.kind,
        row.run_id,
        row.stream_id,
        row.worker_id,
        row.owner_token,
        row.fence,
        row.relayed,
        row.cancellable,
    )


def _busy(row: ConversationExecution) -> RunBusy:
    """Publish occupancy, withholding streams that have no subscriber transport."""
    return RunBusy(
        _target(row),
        row.kind,
        row.phase,
        row.run_id,
        row.stream_id if row.relayed else None,
        row.cancellable,
    )


def _owned(admission: RunAdmission) -> tuple[ColumnElement[bool], ...]:
    """Every transition proves the complete invocation identity, including its fence."""
    row = ConversationExecution
    return (
        row.id == admission.activity_id,
        row.user_id == admission.target.owner_id,
        row.conversation_id == admission.target.id,
        row.conversation_revision == admission.target.revision,
        row.runtime_id == admission.target.runtime_id,
        row.worker_id == admission.worker_id,
        row.owner_token == admission.owner_token,
        row.fence == admission.fence,
        # Billing correlation can be retagged on a HITL resume. Its lost
        # acknowledgement cannot revoke this invocation's unchanged identity.
        row.stream_id == admission.stream_id,
        row.kind == admission.kind,
    )


def _check_run_id(value: str) -> None:
    """Refuse an invalid internal identity before PostgreSQL binds its value."""
    if not value or len(value) > CONVERSATION_RUN_ID_MAX_LENGTH or "\x00" in value:
        raise ValueError("Invalid conversation execution identifier")


class ConversationExecutionRepository(BaseRepository[ConversationExecution]):
    """Flush only; the operation's service owns the single commit or rollback."""

    def __init__(self, db: AsyncSession) -> None:
        """Use a caller-owned session that ends before model or transport work."""
        super().__init__(db, ConversationExecution)

    async def admit(
        self,
        target: ConversationRef,
        *,
        run_id: str,
        stream_id: str,
        worker_id: UUID,
        kind: ExecutionKind = ExecutionKind.GRAPH,
        relayed: bool = False,
        cancellable: bool = False,
    ) -> RunAdmission | RunBusy:
        """Reserve one account slot, never stealing it because of age or a missing TTL.

        Args:
            target: Already resolved, immutable business and runtime identity.
            run_id: Billing correlation, reused only by a HITL continuation.
            stream_id: Fresh invocation transport identity.
            worker_id: The actual supervisor boot UUID, not a reusable process ID.
            kind: Graph slot or independent Live reservation.
            relayed: Whether this invocation serves a reconnectable stream.
            cancellable: Whether its owner observes the browser's stop signal.

        Returns:
            New authority or the owner's existing occupancy, with no takeover.

        Raises:
            ExecutionRevoked: The owner or target is no longer current.
        """
        _check_run_id(run_id)
        _check_run_id(stream_id)
        await hold_owner_lock(self.db, CONVERSATION_OWNER_LOCK_SCOPE, target.owner_id)
        await self._hold_target(target)
        busy = await self.active_for_owner(target.owner_id, kind=kind)
        if busy is not None:
            return busy
        row = ConversationExecution(
            user_id=target.owner_id,
            conversation_id=target.id,
            conversation_kind=target.kind,
            conversation_revision=target.revision,
            runtime_id=target.runtime_id,
            kind=kind,
            run_id=run_id,
            stream_id=stream_id,
            worker_id=worker_id,
            relayed=relayed,
            cancellable=cancellable,
        )
        self.db.add(row)
        await self.db.flush()
        return _admission(row)

    async def _hold_target(self, target: ConversationRef) -> None:
        """Owner then conversation SHARE locks are incompatible with retirement."""
        await hold_conversation_source(self.db, target.owner_id, target)

    async def active_for_owner(
        self, owner_id: UUID, *, kind: ExecutionKind = ExecutionKind.GRAPH
    ) -> RunBusy | None:
        """Read the unique occupying row; closed history never blocks a new turn."""
        row = await self.db.scalar(
            select(ConversationExecution)
            .where(
                ConversationExecution.user_id == owner_id,
                ConversationExecution.kind == kind,
                ConversationExecution.phase != ExecutionPhase.CLOSED,
            )
            .execution_options(populate_existing=True)
        )
        return _busy(row) if row is not None else None

    async def require_current(self, admission: RunAdmission, *, exclusive: bool = False) -> None:
        """Validate the complete target and invocation in one short transaction."""
        await self._hold_target(admission.target)
        await require_current_execution(self.db, admission, exclusive=exclusive)

    async def snapshot_for_owner(
        self,
        owner_id: UUID,
        *,
        stream_id: str | None = None,
    ) -> ExecutionSnapshot | None:
        """Read active graph occupancy or one exact stream, title included in one query.

        Exact-stream reads include CLOSED history so a subscriber can distinguish
        acknowledged completion from a silent or disconnected producer. All reads
        are account-scoped; no private invocation token is projected.
        """
        execution = ConversationExecution
        statement = (
            select(execution, Conversation.title)
            .outerjoin(
                Conversation,
                (Conversation.id == execution.conversation_id)
                & (Conversation.user_id == execution.user_id)
                & (Conversation.revision == execution.conversation_revision)
                & Conversation.deleted_at.is_(None),
            )
            .where(execution.user_id == owner_id, execution.kind == ExecutionKind.GRAPH)
        )
        statement = statement.where(
            (
                execution.stream_id == stream_id
                if stream_id is not None
                else execution.phase != ExecutionPhase.CLOSED
            ),
        )
        result = (
            await self.db.execute(statement.execution_options(populate_existing=True))
        ).one_or_none()
        if result is None:
            return None
        row, title = result
        return ExecutionSnapshot(_busy(row), row.stream_id, row.relayed, row.heartbeat_at, title)

    async def touch(self, admission: RunAdmission) -> bool:
        """Record supervision only; no timestamp ever reopens or transfers authority."""
        found = await self.db.scalar(
            update(ConversationExecution)
            .where(
                *_owned(admission),
                ConversationExecution.phase.in_((ExecutionPhase.RUNNING, ExecutionPhase.DRAINING)),
            )
            .values(heartbeat_at=datetime.now(UTC))
            .returning(ConversationExecution.id)
        )
        return found is not None

    async def mark_draining(self, admission: RunAdmission) -> bool:
        """Stop authorizing new graph work while its actual writers are being joined."""
        return await self._transition(admission, ExecutionPhase.DRAINING, (ExecutionPhase.RUNNING,))

    async def recovery_record(
        self, activity_id: UUID, worker_id: UUID
    ) -> tuple[RunAdmission, ExecutionPhase]:
        """Read one exact boot's activity for server-side operator recovery.

        This privileged door is not exposed by an HTTP route. A worker UUID is
        an identity, never proof that its process exited. The recovery caller
        must establish that separately before closing an occupied activity.
        """
        row = await self.db.scalar(
            select(ConversationExecution)
            .where(
                ConversationExecution.id == activity_id,
                ConversationExecution.worker_id == worker_id,
            )
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise ExecutionRevoked()
        return _admission(row), row.phase

    async def recovering_count(self) -> int:
        """Count occupied graph and voice reservations that require recovery."""
        result = await self.db.execute(
            select(func.count())
            .select_from(ConversationExecution)
            .where(
                ACTIVE_EXECUTION_PREDICATE, ConversationExecution.phase == ExecutionPhase.RECOVERING
            )
        )
        return result.scalar_one()

    async def close_recovered(self, admission: RunAdmission) -> bool:
        """Close a quarantined activity after its worker's stop was established.

        No RUNNING-to-CLOSED shortcut is offered to operator recovery. A lost
        acknowledgement is retryable; no successor has this complete identity.
        A recovered run did not end normally (ADR-384).
        """
        return await self._transition(
            admission,
            ExecutionPhase.CLOSED,
            (ExecutionPhase.RECOVERING,),
            end=RunEnd.INTERRUPTED,
        )

    async def mark_recovering(self, admission: RunAdmission) -> bool:
        """An unacknowledged stop stays occupied; it does not become a free slot."""
        return await self._transition(
            admission,
            ExecutionPhase.RECOVERING,
            (ExecutionPhase.RUNNING, ExecutionPhase.DRAINING),
        )

    async def close_owned(self, admission: RunAdmission, *, end: RunEnd) -> bool:
        """Settle after the owner joined its work; a stale finalizer is a no-op.

        Args:
            admission: The closing invocation's private authority.
            end: How the run ended, as its driver declared it (ADR-384).

        Returns:
            Whether this call closed the activity.
        """
        return await self._transition(
            admission,
            ExecutionPhase.CLOSED,
            (ExecutionPhase.RUNNING, ExecutionPhase.DRAINING, ExecutionPhase.RECOVERING),
            end=end,
        )

    async def open_notes(self, admission: RunAdmission) -> bool:
        """Let the person's notes join this running invocation's answer (ADR-385).

        Args:
            admission: The invocation's private authority.

        Returns:
            Whether this call opened them; False when they already were, or when the
            invocation no longer runs under this exact identity.
        """
        return await self._set_notes(admission, accepts=True)

    async def close_notes(self, admission: RunAdmission) -> bool:
        """Stop taking notes: the loop will call its model no more (ADR-385).

        Args:
            admission: The invocation's private authority.

        Returns:
            Whether this call closed them; False when they were not open.
        """
        return await self._set_notes(admission, accepts=False)

    async def _set_notes(self, admission: RunAdmission, *, accepts: bool) -> bool:
        """Flip the flag on the exact running invocation, only when it changes."""
        changed = await self.db.scalar(
            update(ConversationExecution)
            .where(
                *_owned(admission),
                ConversationExecution.phase == ExecutionPhase.RUNNING,
                ConversationExecution.accepts_notes.is_(not accepts),
            )
            .values(accepts_notes=accepts)
            .returning(ConversationExecution.id)
        )
        return changed is not None

    async def note_stream(self, owner_id: UUID, target: ConversationRef) -> str | None:
        """The stream of the running answer a note for this discussion may join.

        Args:
            owner_id: The account.
            target: The discussion and generation the note was written for.

        Returns:
            The invocation's stream when it runs for exactly this target and takes
            notes now; None otherwise.
        """
        execution = ConversationExecution
        stream_id: str | None = await self.db.scalar(
            select(execution.stream_id).where(
                execution.user_id == owner_id,
                execution.kind == ExecutionKind.GRAPH,
                execution.phase == ExecutionPhase.RUNNING,
                execution.accepts_notes.is_(True),
                execution.conversation_id == target.id,
                execution.conversation_revision == target.revision,
            )
        )
        return stream_id

    async def ended_as(self, owner_id: UUID, stream_id: str) -> RunEnd | None:
        """How one of the owner's invocations ended; None while it runs, or if unknown.

        Args:
            owner_id: The account the invocation belongs to.
            stream_id: The invocation's transport identity.

        Returns:
            The end written at its close, or None.
        """
        return await self.db.scalar(
            select(ConversationExecution.end_state).where(
                ConversationExecution.user_id == owner_id,
                ConversationExecution.stream_id == stream_id,
                ConversationExecution.phase == ExecutionPhase.CLOSED,
            )
        )

    async def _transition(
        self,
        admission: RunAdmission,
        phase: ExecutionPhase,
        sources: tuple[ExecutionPhase, ...],
        *,
        end: RunEnd | None = None,
    ) -> bool:
        """Atomically condition a transition on both authority and source phase.

        Every target phase is past RUNNING, so the invocation stops taking notes in
        the same statement (ADR-385).
        """
        closing = phase == ExecutionPhase.CLOSED
        changed = await self.db.scalar(
            update(ConversationExecution)
            .where(
                *_owned(admission),
                ConversationExecution.phase.in_(sources),
            )
            .values(
                phase=phase,
                closed_at=datetime.now(UTC) if closing else None,
                end_state=end if closing else None,
                # Every transition leaves RUNNING: the loop calls its model no more.
                accepts_notes=False,
            )
            .returning(ConversationExecution.id)
        )
        return changed is not None

    async def retag_run(self, admission: RunAdmission, run_id: str) -> RunAdmission:
        """Keep a resumed question's billing identity on a NEW transport invocation."""
        _check_run_id(run_id)
        changed = await self.db.scalar(
            update(ConversationExecution)
            .where(
                *_owned(admission),
                ConversationExecution.phase == ExecutionPhase.RUNNING,
            )
            .values(run_id=run_id)
            .returning(ConversationExecution.id)
        )
        if changed is None:
            raise ExecutionRevoked()
        return replace(admission, run_id=run_id)
