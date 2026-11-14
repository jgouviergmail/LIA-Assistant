"""Explicit operator recovery of every actual worker in a quarantined Live session."""

from dataclasses import dataclass
from uuid import UUID

import structlog

from src.core.conversation_execution import ExecutionKind, ExecutionPhase
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.reservation_repository import ConversationReservationRepository
from src.infrastructure.database.session import get_db_context
from src.infrastructure.streaming.reservation_work import release_closed_record

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LiveRecoveryStatus:
    """A parent boot is an identity; unfinished child boots are the actual work to stop."""

    phase: ExecutionPhase
    outstanding_workers: frozenset[UUID]


async def inspect_live(activity_id: UUID, worker_id: UUID) -> LiveRecoveryStatus:
    """Read exact operational coordinates without a TTL or an automatic takeover."""
    async with get_db_context() as db:
        admission, phase = await ConversationExecutionRepository(db).recovery_record(
            activity_id, worker_id
        )
        if admission.kind != ExecutionKind.LIVE:
            raise ValueError("This recovery door accepts only Live reservations")
        workers = await ConversationReservationRepository(db).outstanding_workers(admission)
        return LiveRecoveryStatus(phase, workers)


async def quarantine_live(activity_id: UUID, worker_id: UUID) -> LiveRecoveryStatus:
    """Withdraw new work without pretending a provider's pending operation has ended."""
    async with get_db_context() as db:
        admission, _ = await ConversationExecutionRepository(db).recovery_record(
            activity_id, worker_id
        )
        await ConversationReservationRepository(db).quarantine(admission)
    return await inspect_live(activity_id, worker_id)


async def close_live_stopped(
    activity_id: UUID, worker_id: UUID, *, stopped_workers: set[UUID]
) -> LiveRecoveryStatus:
    """Close only after explicit attestation about every unjoined worker; never replay a relay."""
    async with get_db_context() as db:
        admission, _ = await ConversationExecutionRepository(db).recovery_record(
            activity_id, worker_id
        )
        await ConversationReservationRepository(db).close_stopped(
            admission, stopped_workers=stopped_workers
        )
    await release_closed_record(admission)
    result = await inspect_live(activity_id, worker_id)
    logger.warning(
        "live_reservation_recovered",
        activity_id=str(activity_id),
        stopped_workers=len(stopped_workers),
        provider_outcome="unresolved",
    )
    return result
