"""Fenced, short SQL transitions for resumable discussion cleanup."""

from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.core.constants import CONVERSATION_CLEANUP_PAGE_SIZE
from src.core.conversation_target import ConversationRef
from src.core.exceptions import ResourceNotFoundError
from src.core.repository import BaseRepository
from src.core.security.authorization import check_resource_ownership_by_user_id
from src.domains.conversations.cleanup_contracts import CleanupClaim, CleanupPhase, CleanupState
from src.domains.conversations.cleanup_models import ConversationOperation
from src.infrastructure.startup.errors import StartupCompletenessError

CleanupError = Literal["cleanup_failed", "cleanup_refused", "cleanup_cancelled"]
_NEXT = {
    CleanupPhase.CHECKPOINT: CleanupPhase.CONTEXT,
    CleanupPhase.CONTEXT: CleanupPhase.PENDING,
    CleanupPhase.PENDING: CleanupPhase.FILES,
    CleanupPhase.FILES: CleanupPhase.COMPLETE,
}
if set(_NEXT) != set(CleanupPhase) - {CleanupPhase.COMPLETE}:
    raise StartupCompletenessError("Conversation cleanup phase transitions are incomplete")


def _due() -> ColumnElement[bool]:
    """The scheduler and claim share one eligibility predicate."""
    row = ConversationOperation
    return or_(
        row.state == CleanupState.PENDING,
        and_(row.state == CleanupState.RETRY_WAIT, row.next_attempt_at <= func.clock_timestamp()),
        and_(row.state == CleanupState.RUNNING, row.claim_until <= func.clock_timestamp()),
    )


def _owned(claim: CleanupClaim) -> tuple[ColumnElement[bool], ...]:
    """A stale lease is not authority, even before another worker takes it."""
    row = ConversationOperation
    return (
        row.id == claim.operation_id,
        row.user_id == claim.target.owner_id,
        row.runtime_id == claim.target.runtime_id,
        row.owner_token == claim.owner_token,
        row.fence == claim.fence,
        row.state == CleanupState.RUNNING,
        row.claim_until > func.clock_timestamp(),
    )


def _snapshot(row: ConversationOperation) -> CleanupClaim:
    """No ORM object or session crosses the external-work boundary."""
    if row.owner_token is None:
        raise RuntimeError("Cleanup claim has no owner")
    return CleanupClaim(
        row.id,
        ConversationRef(
            row.user_id,
            row.conversation_id,
            row.conversation_kind,
            row.old_revision,
            row.runtime_id,
        ),
        row.owner_token,
        row.fence,
        row.phase,
        tuple(row.attachment_ids),
    )


class ConversationCleanupRepository(BaseRepository[ConversationOperation]):
    """The caller commits each claim/renewal/acknowledgement before any wait."""

    def __init__(self, db: AsyncSession) -> None:
        """Use a session owned by one short cleanup transition."""
        super().__init__(db, ConversationOperation)

    async def outstanding_by_state(self) -> dict[CleanupState, tuple[int, datetime]]:
        """Count exact durable debt and its oldest creation time in one grouped read."""
        row = ConversationOperation
        result = await self.db.execute(
            select(row.state, func.count(), func.min(row.created_at))
            .where(
                row.state.in_(
                    tuple(state for state in CleanupState if state != CleanupState.SUCCEEDED)
                )
            )
            .group_by(row.state)
        )
        return {state: (count, oldest) for state, count, oldest in result.tuples()}

    async def require_requested(self, owner: UUID, request_id: UUID) -> ConversationOperation:
        """A receipt is private even after its discussion no longer exists."""
        row = await self.db.scalar(
            select(ConversationOperation)
            .where(
                ConversationOperation.user_id == owner,
                ConversationOperation.request_id == request_id,
            )
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise ResourceNotFoundError("conversation_operation")
        check_resource_ownership_by_user_id(
            row, owner, "conversation_operation", hide_existence=True
        )
        return row

    async def claim(
        self, *, lease_seconds: int, operation_id: UUID | None = None
    ) -> CleanupClaim | None:
        """Claim one due operation, or safely take over an expired cleanup lease.

        This lease applies only to idempotent deletion of an immutable retired
        runtime. It never declares a graph writer dead or grants graph admission.
        """
        row = ConversationOperation
        statement = (
            select(row)
            .where(_due())
            .order_by(row.created_at, row.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if operation_id is not None:
            statement = statement.where(row.id == operation_id)
        found = await self.db.scalar(statement.execution_options(populate_existing=True))
        if found is None:
            return None
        # Let PostgreSQL decide the deadline; no worker clock can extend it.
        await self.db.execute(
            update(row)
            .where(row.id == found.id)
            .values(
                state=CleanupState.RUNNING,
                owner_token=uuid4(),
                fence=row.fence + 1,
                attempts=row.attempts + 1,
                next_attempt_at=None,
                error_code=None,
                claim_until=func.clock_timestamp() + timedelta(seconds=lease_seconds),
            )
        )
        await self.db.refresh(found)
        return _snapshot(found)

    async def renew(self, claim: CleanupClaim, *, lease_seconds: int) -> bool:
        """Renew only the current unexpired token, including during a slow phase."""
        result = await self.db.scalar(
            update(ConversationOperation)
            .where(*_owned(claim))
            .values(claim_until=func.clock_timestamp() + timedelta(seconds=lease_seconds))
            .returning(ConversationOperation.id)
        )
        return result is not None

    async def advance(self, claim: CleanupClaim) -> bool:
        """Acknowledge one explicit success; a duplicate cannot skip another phase."""
        next_phase = _NEXT.get(claim.phase)
        if next_phase is None:
            return False
        row = await self.db.scalar(
            select(ConversationOperation)
            .where(
                *_owned(claim),
                ConversationOperation.phase == claim.phase,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            return False
        row.phase = next_phase
        if next_phase == CleanupPhase.COMPLETE:
            row.state = CleanupState.SUCCEEDED
            row.owner_token, row.claim_until = None, None
            row.completed_at = await self.db.scalar(select(func.clock_timestamp()))
        await self.db.flush()
        return True

    async def fail(
        self,
        claim: CleanupClaim,
        *,
        error_code: CleanupError,
        max_attempts: int,
        retry_seconds: int,
    ) -> bool:
        """Retain the failed phase and exact targets, without expiring unresolved debt."""
        row = await self.db.scalar(
            select(ConversationOperation)
            .where(*_owned(claim))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            return False
        row.state = (
            CleanupState.NEEDS_ATTENTION
            if row.attempts >= max_attempts
            else CleanupState.RETRY_WAIT
        )
        row.owner_token, row.claim_until = None, None
        row.error_code = error_code
        row.next_attempt_at = None
        await self.db.flush()
        if row.state == CleanupState.RETRY_WAIT:
            await self.db.execute(
                update(ConversationOperation)
                .where(ConversationOperation.id == row.id)
                .values(next_attempt_at=func.clock_timestamp() + timedelta(seconds=retry_seconds))
            )
        return True

    async def expire_completed(self, *, before: datetime) -> int:
        """Expire only explicitly successful tombstones, never a failed cleanup."""
        selected = (
            select(ConversationOperation.id)
            .where(
                ConversationOperation.state == CleanupState.SUCCEEDED,
                ConversationOperation.completed_at < before,
            )
            .order_by(ConversationOperation.completed_at, ConversationOperation.id)
            .limit(CONVERSATION_CLEANUP_PAGE_SIZE)
        )
        deleted = await self.db.scalars(
            delete(ConversationOperation)
            .where(
                ConversationOperation.id.in_(selected),
            )
            .returning(ConversationOperation.id)
        )
        return len(deleted.all())

    async def due_ids(self, *, limit: int) -> list[UUID]:
        """Read a bounded candidate page; each later act still must claim its row."""
        return list(
            await self.db.scalars(
                select(ConversationOperation.id)
                .where(_due())
                .order_by(
                    ConversationOperation.created_at,
                    ConversationOperation.id,
                )
                .limit(limit)
            )
        )

    async def retry_requested(self, owner: UUID, request_id: UUID) -> ConversationOperation:
        """Explicitly re-arm failed debt without changing its original act or target."""
        existing = await self.require_requested(owner, request_id)
        row = await self.db.scalar(
            select(ConversationOperation)
            .where(
                ConversationOperation.id == existing.id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise ResourceNotFoundError("conversation_operation")
        if row.state == CleanupState.NEEDS_ATTENTION:
            row.state = CleanupState.PENDING
            row.attempts, row.error_code, row.next_attempt_at = 0, None, None
            await self.db.flush()
        return row
