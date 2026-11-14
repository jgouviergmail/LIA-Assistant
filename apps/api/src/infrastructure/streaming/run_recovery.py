"""Explicit graph recovery after an operator establishes the owning worker's death.

There is intentionally no scheduler, TTL takeover or automatic replay here.
Quarantine removes authority while retaining occupancy. Only the privileged
server command may attest that the exact boot has stopped, then close it.
"""

import asyncio
from uuid import UUID

import structlog

from src.core.constants import CONVERSATION_OWNER_LOCK_SCOPE, STREAM_TEARDOWN_WAIT_SECONDS
from src.core.conversation_execution import ExecutionKind, ExecutionPhase, RunAdmission, RunEnd
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.waiting_repository import (
    NOTHING_SETTLED,
    WaitingMessageRepository,
)
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database.owner_lock import hold_owner_lock
from src.infrastructure.database.session import get_db_context
from src.infrastructure.streaming.release_listener import announce_release
from src.infrastructure.streaming.run_admission import count_settled
from src.infrastructure.streaming.runtime_redis import close_runtime_writes

logger = structlog.get_logger(__name__)


async def inspect_execution(activity_id: UUID, worker_id: UUID) -> ExecutionPhase:
    """Inspect one exact graph without changing it or interpreting heartbeat age."""
    _, phase = await _record(activity_id, worker_id)
    return phase


async def _record(activity_id: UUID, worker_id: UUID) -> tuple[RunAdmission, ExecutionPhase]:
    """Keep operator recovery separate from Live's provider/session closing protocol."""
    async with get_db_context() as db:
        admission, phase = await ConversationExecutionRepository(db).recovery_record(
            activity_id, worker_id
        )
    if admission.kind != ExecutionKind.GRAPH:
        raise ValueError("Voice reservations require their session closing protocol")
    return admission, phase


async def _revoke_redis(admission: RunAdmission) -> None:
    """A timeout leaves SQL occupied; a newer Redis grant is never removed."""
    async with asyncio.timeout(STREAM_TEARDOWN_WAIT_SECONDS):
        await close_runtime_writes(await get_redis_cache(), admission)


async def quarantine(activity_id: UUID, worker_id: UUID) -> ExecutionPhase:
    """Commit write revocation before Redis I/O, without claiming the producer ended.

    The owner will observe revocation on its heartbeat or its next guarded
    operation. An external request already sent may still finish: inspect its
    ledger/provider outcome instead of replaying the instruction.
    """
    admission, phase = await _record(activity_id, worker_id)
    if phase == ExecutionPhase.CLOSED:
        return phase
    async with get_db_context() as db:
        await ConversationExecutionRepository(db).mark_recovering(admission)
    logger.warning(
        "conversation_execution_quarantined", activity_id=str(activity_id), worker_id=str(worker_id)
    )
    await _revoke_redis(admission)
    return await inspect_execution(activity_id, worker_id)


async def close_stopped(activity_id: UUID, confirmed_stopped_worker_id: UUID) -> ExecutionPhase:
    """Release one quarantined graph after an explicit operator stop attestation.

    Args:
        activity_id: The exact quarantined invocation, never a whole account.
        confirmed_stopped_worker_id: Boot whose process and owned children the
            operator has verified stopped. A missing heartbeat is NOT proof.

    Returns:
        CLOSED after conditional SQL settlement, including an idempotent retry.

    Raises:
        ValueError: The activity was not quarantined or is a Live reservation.
        ExecutionRevoked: The supplied boot does not own that activity.
        TimeoutError: Redis revocation is unacknowledged; occupancy remains.
    """
    admission, phase = await _record(activity_id, confirmed_stopped_worker_id)
    if phase == ExecutionPhase.CLOSED:
        return phase
    if phase != ExecutionPhase.RECOVERING:
        raise ValueError("Quarantine the graph before confirming its worker stopped")
    await _revoke_redis(admission)
    settled = NOTHING_SETTLED
    async with get_db_context() as db:
        await hold_owner_lock(db, CONVERSATION_OWNER_LOCK_SCOPE, admission.target.owner_id)
        changed = await ConversationExecutionRepository(db).close_recovered(admission)
        if changed:
            # A dead run did not end normally: what waited is held (ADR-384).
            settled = await WaitingMessageRepository(db).settle_release(
                admission.target.owner_id, admission.stream_id, RunEnd.INTERRUPTED
            )
    count_settled(settled)
    if changed:
        announce_release(admission.target.owner_id, RunEnd.INTERRUPTED)
    logger.warning(
        "conversation_execution_recovered",
        activity_id=str(activity_id),
        worker_id=str(confirmed_stopped_worker_id),
        changed=changed,
        provider_outcome="unresolved",
    )
    return await inspect_execution(activity_id, confirmed_stopped_worker_id)
