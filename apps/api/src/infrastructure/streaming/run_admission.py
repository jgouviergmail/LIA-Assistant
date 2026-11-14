"""Durable graph admission and supervision independent of the SSE transport's lifetime."""

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import structlog

from src.core.config import settings
from src.core.constants import CONVERSATION_OWNER_LOCK_SCOPE, STREAM_TEARDOWN_WAIT_SECONDS
from src.core.conversation_execution import (
    ConversationBusy,
    ExecutionRevoked,
    RunAdmission,
    RunBusy,
    RunEnd,
)
from src.core.conversation_target import ConversationRef
from src.core.run_authority import RunAuthority, current_run_authority, run_authority_scope
from src.core.worker_identity import WORKER_BOOT_ID as WORKER_BOOT_ID
from src.domains.conversations.catalogue_service import (
    ConversationCatalogueService,
    conversation_ref,
)
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.waiting_repository import (
    NOTHING_SETTLED,
    SettledRelease,
    WaitingMessageRepository,
)
from src.infrastructure.async_utils import cancel_and_join, finish_owned_task, safe_fire_and_forget
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database.owner_lock import hold_owner_lock
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.metrics_agents import chat_waiting_messages_total
from src.infrastructure.streaming.release_listener import announce_release
from src.infrastructure.streaming.runtime_redis import close_runtime_writes, open_runtime_writes

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def execution_for_turn(
    owner_id: UUID,
    *,
    target: ConversationRef | None,
    admission: RunAdmission | None,
    run_id: str | None,
    language: str | None,
) -> AsyncIterator[RunAuthority]:
    """Legacy callers select Main; a prepared producer lends its exact admission.

    Args:
        owner_id: The authenticated or internal caller's account.
        target: Frozen target from a prior owner-checked resolution, if supplied.
        admission: The producer's private authority, never parsed from a request.
        run_id: Billing correlation; a borrowed admission already owns it.
        language: Explicit account locale for first-use Main creation.

    Raises:
        ConversationBusy: Another invocation still occupies the account.
        ExecutionRevoked: Supplied coordinates disagree or have been retired.
    """
    current = current_run_authority()
    if admission is None and current is not None:
        admission = current.admission
    if admission is not None:
        _require_matching_admission(owner_id, target, admission, run_id)
    else:
        admission = await _admit_legacy_turn(owner_id, target, run_id, language)
    async with owned_execution(admission) as authority:
        yield authority


def _require_matching_admission(
    owner_id: UUID, target: ConversationRef | None, admission: RunAdmission, run_id: str | None
) -> None:
    """A borrowed authority cannot change account, generation or billing identity."""
    if admission.target.owner_id != owner_id or (target is not None and target != admission.target):
        raise ExecutionRevoked()
    if run_id is not None and run_id != admission.run_id:
        raise ExecutionRevoked()


async def _admit_legacy_turn(
    owner_id: UUID, target: ConversationRef | None, run_id: str | None, language: str | None
) -> RunAdmission:
    """Resolve Main only for an untargeted producer, then reserve its exact runtime."""
    if target is None:
        async with get_db_context() as db:
            row = await ConversationCatalogueService(db).ensure_primary_row(owner_id, language)
            target = conversation_ref(row)
    if target.owner_id != owner_id:
        raise ExecutionRevoked()
    result = await reserve_execution(
        target, run_id=run_id or str(uuid4()), stream_id=str(uuid4()), relayed=False
    )
    if isinstance(result, RunBusy):
        raise ConversationBusy(result)
    return result


async def reserve_execution(
    target: ConversationRef,
    *,
    run_id: str,
    stream_id: str,
    relayed: bool,
    cancellable: bool = False,
) -> RunAdmission | RunBusy:
    """Commit admission before any provider call or response headers leave.

    Args:
        target: Already resolved immutable conversation generation.
        run_id: Billing correlation, shared by a question and its continuation.
        stream_id: Fresh invocation identity, never reused on a continuation.
        relayed: Whether a browser can subscribe to this invocation's stream.
        cancellable: Whether the producer observes browser cancellation.

    Returns:
        Private authority or the account's existing occupancy.
    """
    claim = asyncio.create_task(
        _reserve(
            target, run_id=run_id, stream_id=stream_id, relayed=relayed, cancellable=cancellable
        )
    )
    try:
        return await asyncio.shield(claim)
    except asyncio.CancelledError:
        # Headers and provider work have not started. Own the commit's outcome
        # through repeated cancellation, then release only this unused claim.
        await finish_owned_task(asyncio.create_task(_abandon_reservation(claim)))
        raise


async def _reserve(
    target: ConversationRef,
    *,
    run_id: str,
    stream_id: str,
    relayed: bool,
    cancellable: bool,
) -> RunAdmission | RunBusy:
    """Retain the minted authority even if the commit acknowledgment is lost."""
    result: RunAdmission | RunBusy | None = None
    try:
        async with get_db_context() as db:
            result = await ConversationExecutionRepository(db).admit(
                target,
                run_id=run_id,
                stream_id=stream_id,
                worker_id=WORKER_BOOT_ID,
                relayed=relayed,
                cancellable=cancellable,
            )
    except Exception, asyncio.CancelledError:
        if isinstance(result, RunAdmission):
            unused = RunAuthority(result, end=RunEnd.UNSTARTED)
            await finish_owned_task(asyncio.create_task(_close_execution(unused)))
        raise
    if isinstance(result, RunAdmission):
        logger.info(
            "conversation_execution_reserved",
            activity_id=str(result.activity_id),
            worker_id=str(result.worker_id),
            process_id=os.getpid(),
        )
    return result


async def _abandon_reservation(claim: asyncio.Task[RunAdmission | RunBusy]) -> None:
    """A cancelled requester never returns with an unowned committed admission."""
    result = await claim
    if isinstance(result, RunAdmission):
        await _close_execution(RunAuthority(result, end=RunEnd.UNSTARTED))


async def release_unstarted_execution(admission: RunAdmission, *, announce: bool = True) -> None:
    """Release only a producer proven cancelled before its first instruction.

    The spawn callback owns that proof. An elapsed timeout, absent Redis key
    or running producer must never use this short path. No run happened: its
    end is ``UNSTARTED``, which holds no waiting message (ADR-384).

    Args:
        admission: The unused admission.
        announce: Whether the release is handed to the release listener. The
            waiting-message departure releases its own refused attempts without
            it: it goes on with its queue, and an announcement would start a
            second departure for the same refusal.
    """
    await _close_execution(RunAuthority(admission, end=RunEnd.UNSTARTED), announce=announce)


@asynccontextmanager
async def owned_execution(admission: RunAdmission) -> AsyncIterator[RunAuthority]:
    """Own the producer and its real writers; nested callers only borrow authority.

    An SSE done chunk, elapsed TTL, or cancellation request does not close this
    activity. A writer that has not joined leaves RECOVERING behind, supervised
    by an owned finalizer. A worker crash leaves it occupied for explicit recovery.
    """
    current = current_run_authority()
    if current is not None:
        current.require_current()
        if current.admission != admission:
            raise ExecutionRevoked()
        yield current
        return
    authority = RunAuthority(admission)
    body = asyncio.current_task()
    assert body is not None
    with run_authority_scope(authority):
        heartbeat: asyncio.Task[None] | None = None
        try:
            await open_runtime_writes(await get_redis_cache(), admission)
            heartbeat = asyncio.create_task(_heartbeat(authority, body))
            yield authority
        except asyncio.CancelledError:
            if authority.supervision_lost:
                raise ExecutionRevoked() from None
            raise
        finally:
            authority.revoked = True
            await finish_owned_task(asyncio.create_task(_finish_execution(authority, heartbeat)))


async def authorize_external_work() -> None:
    """Ask durable authority immediately before a graph starts a paid call or effect.

    Independent account work has no graph admission. Graph callers retain no
    transaction while the provider answers; the marked invocation must never be
    automatically replayed after an unknown provider outcome.
    """
    authority = current_run_authority()
    if authority is None:
        return
    authority.require_current()
    async with get_db_context() as db:
        await ConversationExecutionRepository(db).require_current(authority.admission)
    authority.require_current()
    authority.external_work_started = True


async def _heartbeat(authority: RunAuthority, body: asyncio.Task[object]) -> None:
    """A failed supervision check revokes before cancelling the producer."""
    while True:
        await asyncio.sleep(settings.background_runs_heartbeat_seconds)
        try:
            async with get_db_context() as db:
                valid = await ConversationExecutionRepository(db).touch(authority.admission)
            if valid:
                await open_runtime_writes(await get_redis_cache(), authority.admission)
        except Exception as exc:
            logger.warning(
                "conversation_execution_heartbeat_failed",
                activity_id=str(authority.admission.activity_id),
                error_type=type(exc).__name__,
            )
            valid = False
        if not valid:
            authority.revoked = True
            authority.supervision_lost = True
            body.cancel()
            return


async def _finish_execution(
    authority: RunAuthority,
    heartbeat: asyncio.Task[None] | None,
) -> None:
    """Revoke, drain for the UI's bound, then retain ownership of an unknown stop."""
    if heartbeat is not None:
        await cancel_and_join(heartbeat)
    revoked = await _revoke_writes(authority)
    writers = tuple(task for task in authority.writers if not task.done())
    for task in writers:
        if not task.cancelling():
            task.cancel()
    if writers:
        _, pending = await asyncio.wait(writers, timeout=STREAM_TEARDOWN_WAIT_SECONDS)
        if pending:
            await _mark_recovering(authority)
            logger.warning(
                "conversation_execution_recovering",
                activity_id=str(authority.admission.activity_id),
                pending_writers=len(pending),
            )
            # This owner remains indexed and is drained on shutdown. Its task
            # inherits no graph authority and can only join/settle this admission.
            with run_authority_scope(None):
                safe_fire_and_forget(
                    _join_and_close(authority, writers),
                    name="conversation_execution_drain",
                )
            return
    if revoked and await _try_close(authority):
        return
    await _mark_recovering(authority)
    with run_authority_scope(None):
        safe_fire_and_forget(_retry_close(authority), name="conversation_execution_recovery")


async def _revoke_writes(authority: RunAuthority) -> bool:
    """Commit SQL revocation before Redis closure; either outage keeps the slot occupied."""
    try:
        async with get_db_context() as db:
            await ConversationExecutionRepository(db).mark_draining(authority.admission)
        # False means an even newer owner already replaced this grant. It
        # cannot authorize THIS invocation, so its writes are also revoked.
        await close_runtime_writes(await get_redis_cache(), authority.admission)
        return True
    except Exception as exc:
        logger.warning(
            "conversation_execution_revocation_failed",
            activity_id=str(authority.admission.activity_id),
            error_type=type(exc).__name__,
        )
        return False


async def _mark_recovering(authority: RunAuthority) -> None:
    """A database outage leaves the previous occupied phase, never a false closure."""
    try:
        async with get_db_context() as db:
            await ConversationExecutionRepository(db).mark_recovering(authority.admission)
    except Exception as exc:
        logger.warning(
            "conversation_execution_recovery_unrecorded",
            activity_id=str(authority.admission.activity_id),
            error_type=type(exc).__name__,
        )


async def _try_close(authority: RunAuthority) -> bool:
    """After actual joins, a lost commit acknowledgement is safe to retry conditionally."""
    try:
        await _close_execution(authority)
        return True
    except Exception as exc:
        logger.warning(
            "conversation_execution_closure_failed",
            activity_id=str(authority.admission.activity_id),
            error_type=type(exc).__name__,
        )
        return False


async def _retry_close(authority: RunAuthority) -> None:
    """Retry this owner's settlement only; cancellation leaves durable occupancy behind."""
    while True:
        if await _revoke_writes(authority) and await _try_close(authority):
            return
        await asyncio.sleep(settings.background_runs_heartbeat_seconds)


async def _join_and_close(
    authority: RunAuthority, writers: tuple[asyncio.Task[object], ...]
) -> None:
    """A second cancellation is not permission to release an unjoined writer."""

    async def join() -> None:
        await asyncio.gather(*writers, return_exceptions=True)

    await finish_owned_task(asyncio.create_task(join()))
    await _retry_close(authority)


def count_settled(settled: SettledRelease) -> None:
    """Count what one release did to the account's waiting messages.

    Args:
        settled: The close's settlement: messages held, notes given back unread.
    """
    if settled.held:
        chat_waiting_messages_total.labels(event="held").inc(settled.held)
    if settled.returned:
        chat_waiting_messages_total.labels(event="note_returned").inc(settled.returned)


async def _close_execution(authority: RunAuthority, *, announce: bool = True) -> None:
    """A stale finalizer cannot close another invocation, even with the same run id.

    The close writes how the run ended — an end its driver did not declare is an
    interrupted one — and settles the account's waiting messages in the same
    transaction; once committed, the release is announced (ADR-384).
    """
    authority.clear_payloads()
    admission = authority.admission
    end = authority.end or RunEnd.INTERRUPTED
    settled = NOTHING_SETTLED
    async with get_db_context() as db:
        # The keep of a waiting message decides under this lock (ADR-384): a message
        # kept while this close waits is settled by it, never left behind it.
        await hold_owner_lock(db, CONVERSATION_OWNER_LOCK_SCOPE, admission.target.owner_id)
        closed = await ConversationExecutionRepository(db).close_owned(admission, end=end)
        if closed:
            settled = await WaitingMessageRepository(db).settle_release(
                admission.target.owner_id, admission.stream_id, end
            )
    count_settled(settled)
    logger.info(
        "conversation_execution_closed",
        activity_id=str(admission.activity_id),
        closed=closed,
        end=end.value,
    )
    if closed and announce:
        announce_release(admission.target.owner_id, end)
