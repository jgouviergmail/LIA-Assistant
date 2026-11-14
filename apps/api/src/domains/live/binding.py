"""Bind every Live request to its original discussion and durable worker contribution."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from src.core.conversation_execution import ExecutionKind, ExecutionRevoked, ReservedWork, RunBusy
from src.core.conversation_selection import ConversationSelection
from src.core.reservation_work import current_reserved_work
from src.core.worker_identity import WORKER_BOOT_ID
from src.domains.conversations.catalogue_service import ConversationCatalogueService
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.reservation_repository import ConversationReservationRepository
from src.domains.live.errors import raise_live_session_in_progress, raise_live_session_not_found
from src.infrastructure.async_utils import finish_owned_task
from src.infrastructure.streaming.live_binding import bind_record
from src.infrastructure.streaming.reservation_work import (
    close_failed_opening,
    commit_work,
    owned_work,
    unknown_work,
)
from src.infrastructure.utils.request_outcome import outcome_unknown

if TYPE_CHECKING:
    from src.domains.live.service import LiveService
    from src.domains.users.models import User


@asynccontextmanager
async def session_work(
    service: LiveService, user: User, session_id: str, *, language: str, closing: bool = False
) -> AsyncIterator[ReservedWork]:
    """Commit a request's claim before work; closing excludes subsequent requests."""
    await service.db.commit()
    record = await service._owned_record(user, session_id, language=language)
    try:
        _, admission = await bind_record(
            service.db, await service._store(), record, language=language
        )
        repo = ConversationReservationRepository(service.db)
        work = (
            await repo.begin_closing(admission, worker_id=WORKER_BOOT_ID)
            if closing
            else await repo.begin(admission, worker_id=WORKER_BOOT_ID, purpose="request")
        )
        await commit_work(service.db, work)
    except ExecutionRevoked:
        await service.db.rollback()
        raise_live_session_not_found(language)
    async with owned_work(work):
        try:
            yield work
        except ExecutionRevoked:
            await service.db.rollback()
            raise_live_session_not_found(language)
        except BaseException:
            await service.db.rollback()
            if closing:
                await unknown_work(work)
            raise
        finally:
            # No publication transaction may outlive its request's contribution.
            await finish_owned_task(asyncio.create_task(service.db.rollback()))


@asynccontextmanager
async def opening_work(
    service: LiveService,
    user: User,
    selection: ConversationSelection,
    *,
    session_id: str,
    run_id: str,
    language: str,
) -> AsyncIterator[ReservedWork]:
    """Reserve before provider setup or mint; only an unused failed start can be released."""
    target = await ConversationCatalogueService(service.db).resolve_target(
        user.id, selection, create_primary=True
    )
    if target is None:
        raise ExecutionRevoked()
    admission = await ConversationExecutionRepository(service.db).admit(
        target,
        run_id=run_id,
        stream_id=session_id,
        worker_id=WORKER_BOOT_ID,
        kind=ExecutionKind.LIVE,
    )
    if isinstance(admission, RunBusy):
        raise_live_session_in_progress(language)
    repo = ConversationReservationRepository(service.db)
    work = await repo.begin(admission, worker_id=WORKER_BOOT_ID, purpose="opening")
    await commit_work(service.db, work)
    async with owned_work(work):
        try:
            yield work
        except BaseException:
            await close_failed_opening(service.db, work)
            raise


async def quarantine_uncertain(error: BaseException) -> None:
    """A sent operation with no known answer is not a safe fresh start."""
    if isinstance(error, asyncio.CancelledError) or outcome_unknown(error):
        work = current_reserved_work()
        if work is not None:
            await unknown_work(work)
