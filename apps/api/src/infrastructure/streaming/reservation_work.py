"""Join voice contributions across workers without holding SQL across their work."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversation_execution import ReservedWork, RunAdmission
from src.core.reservation_work import require_reserved_work, reservation_work_scope
from src.core.worker_identity import WORKER_BOOT_ID
from src.domains.conversations.reservation_repository import ConversationReservationRepository
from src.domains.live.session_store import LiveSessionStore
from src.infrastructure.async_utils import finish_owned_task
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)


async def _compensate_commit(
    db: AsyncSession, commit: asyncio.Task[None], work: ReservedWork
) -> None:
    """Join the original commit before touching its session or compensating its row."""
    try:
        await commit
    except Exception as error:
        # The caller propagates the admission failure. Its SQL outcome is
        # established below using the complete private identity, never guessed.
        logger.debug("live_admission_commit_failed", error_type=type(error).__name__)
    await db.rollback()
    async with get_db_context() as fresh:
        await ConversationReservationRepository(fresh).abandon_unstarted(work)


async def commit_work(db: AsyncSession, work: ReservedWork) -> None:
    """Commit before running; cancellation joins and compensates before returning."""
    commit = asyncio.create_task(db.commit())
    try:
        await asyncio.shield(commit)
    except BaseException:
        await finish_owned_task(asyncio.create_task(_compensate_commit(db, commit, work)))
        raise


async def close_failed_opening(db: AsyncSession, work: ReservedWork) -> None:
    """Release caller locks and settle a failed start through repeated cancellation."""

    async def settle() -> None:
        await db.rollback()
        async with get_db_context() as fresh:
            await ConversationReservationRepository(fresh).close_failed_opening(work)

    await finish_owned_task(asyncio.create_task(settle()))


async def require_live_work() -> None:
    """Recheck the actual contribution before each new provider effect, then release SQL."""
    work = require_reserved_work()
    async with get_db_context() as db:
        await ConversationReservationRepository(db).require_current(work)


async def release_closed_record(admission: RunAdmission) -> None:
    """Remove only the exact closed reservation's cache, retryable after a lost acknowledgment."""
    store = LiveSessionStore(await get_redis_cache())
    record = await store.get(admission.target.owner_id)
    if record is not None and record.lia_activity_id == admission.activity_id:
        await store.release(record.user_id, record.token)


async def finish_work(work: ReservedWork) -> None:
    """Write an actual join, through repeated cancellation, before the task disappears."""

    async def settle() -> None:
        async with get_db_context() as db:
            repository = ConversationReservationRepository(db)
            await repository.finish(work)
            closed = await repository.is_closed(work.admission)
        if closed:
            await release_closed_record(work.admission)

    await finish_owned_task(asyncio.create_task(settle()))


async def unknown_work(work: ReservedWork) -> None:
    """Retain an unacknowledged provider operation instead of relaunching it."""

    async def quarantine() -> None:
        async with get_db_context() as db:
            await ConversationReservationRepository(db).mark_unknown(work)

    await finish_owned_task(asyncio.create_task(quarantine()))


async def fork_relay(work: ReservedWork) -> ReservedWork:
    """Commit a relay's own contribution before scheduling it or releasing its parent."""
    child = None
    try:
        async with get_db_context() as db:
            child = await ConversationReservationRepository(db).fork(
                work, worker_id=WORKER_BOOT_ID, purpose="relay"
            )
            await commit_work(db, child)
        return child
    except BaseException:
        # Context exit is an await too. The caller does not own this child
        # until the whole session has closed and the function has returned.
        if child is not None:
            await finish_work(child)
        raise


@asynccontextmanager
async def owned_work(work: ReservedWork) -> AsyncIterator[None]:
    """Keep source identity while running and settle only once the actual body exits."""
    with reservation_work_scope(work):
        try:
            yield
        finally:
            await finish_work(work)
