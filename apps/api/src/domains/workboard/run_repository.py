"""Durable ticket claims: start only while owned, and never replay an unknown act."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CursorResult, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversation_execution import ExecutionPhase
from src.core.repository import BaseRepository
from src.domains.conversations.execution_models import ConversationExecution
from src.domains.workboard.constants import RunError, RunOutcome, TicketStatus
from src.domains.workboard.models import WorkboardTicket


class WorkboardRunRepository(BaseRepository[WorkboardTicket]):
    """Claim and retirement transitions share the caller's short transaction."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, WorkboardTicket)

    async def claim_ticket(
        self,
        ticket: WorkboardTicket,
        *,
        run_id: str,
        now: datetime,
    ) -> WorkboardTicket | None:
        """Recheck eligibility in the same statement that takes the claim.

        Args:
            ticket: The row offered by the locking scan.
            run_id: Unique token of this ticket invocation.
            now: Claim time, in UTC.

        Returns:
            The claimed row, or None when eligibility changed.
        """
        return (
            await self.db.execute(
                update(WorkboardTicket)
                .where(
                    WorkboardTicket.id == ticket.id,
                    WorkboardTicket.status == TicketStatus.TODO.value,
                    WorkboardTicket.run_claimed_at.is_(None),
                )
                .values(
                    status=TicketStatus.IN_PROGRESS.value,
                    status_changed_at=now,
                    run_claimed_at=now,
                    run_attempts=WorkboardTicket.run_attempts + 1,
                    run_count=WorkboardTicket.run_count + 1,
                    last_run_id=run_id,
                )
                .returning(WorkboardTicket)
            )
        ).scalar_one_or_none()

    async def lock_owned_run(self, ticket_id: UUID, run_id: str) -> bool:
        """Lock a current claim until its start event commits.

        Args:
            ticket_id: The ticket whose claimed work is about to start.
            run_id: The claim token originally handed to the worker.

        Returns:
            False after a move, deletion, retirement or replacement of the claim.
        """
        return (
            await self.db.scalar(
                select(WorkboardTicket.id)
                .where(
                    WorkboardTicket.id == ticket_id,
                    WorkboardTicket.last_run_id == run_id,
                    WorkboardTicket.status == TicketStatus.IN_PROGRESS.value,
                    WorkboardTicket.run_claimed_at.is_not(None),
                )
                .with_for_update()
            )
            is not None
        )

    async def reap_stale_claims(self, *, older_than: datetime) -> int:
        """Retire unknown outcomes without requeuing or stealing a durable execution.

        Args:
            older_than: Claims older than this instant may have lost their worker.

        Returns:
            The number retired. A running, draining or recovering graph protects
            its claim regardless of heartbeat age. Retired work stays in progress
            with an explicit error until the person decides what to do next.
        """
        occupied = exists().where(
            ConversationExecution.user_id
            == func.coalesce(
                WorkboardTicket.assignee_user_id,
                WorkboardTicket.owner_user_id,
            ),
            ConversationExecution.run_id == WorkboardTicket.last_run_id,
            ConversationExecution.phase != ExecutionPhase.CLOSED,
        )
        result = await self.db.execute(
            update(WorkboardTicket)
            .where(
                WorkboardTicket.status == TicketStatus.IN_PROGRESS.value,
                WorkboardTicket.run_claimed_at.is_not(None),
                WorkboardTicket.run_claimed_at < older_than,
                ~occupied,
            )
            .values(
                run_claimed_at=None,
                last_run_outcome=RunOutcome.FAILED.value,
                last_run_error=RunError.RUN_REAPED.value,
            )
        )
        assert isinstance(result, CursorResult)
        return result.rowcount
