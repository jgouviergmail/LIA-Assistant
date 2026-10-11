"""Owned renewal brackets slow native source calls on independent SQL sessions."""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import TypeVar

from src.core.config import settings
from src.domains.rag_spaces.jobs_repository import (
    DRIVE_SOURCE_TABLE,
    MAIL_SOURCE_TABLE,
    RAGJobsRepository,
)
from src.domains.rag_spaces.source_worker_lease import (
    SourceLeaseLost,
    SourceWorkerLease,
    current_source_worker,
    require_source_worker,
    source_worker_scope,
)
from src.infrastructure.database.session import get_db_context

T = TypeVar("T")


async def run_native_source_worker(scope: SourceWorkerLease) -> None:
    """The native launcher carries the original unique claim into Source workers."""
    with source_worker_scope(scope):
        await renew_native_source()
        if scope.kind == "drive":
            from src.domains.rag_spaces.drive_sync import sync_folder_background

            await sync_folder_background(scope.space_id, scope.source_id, scope.actor_id)
        else:
            from src.domains.rag_spaces.mail_sync import sync_label_background

            await sync_label_background(scope.source_id, scope.actor_id)


def _heartbeat_interval() -> float:
    return max(0.1, settings.rag_job_lease_ttl_seconds / 3)


async def renew_native_source() -> None:
    scope = current_source_worker()
    if scope is None:
        return
    async with get_db_context() as db:
        await require_source_worker(db)
        renewed = await RAGJobsRepository(db).heartbeat_source(
            scope.source_id,
            settings.rag_job_lease_ttl_seconds,
            table=DRIVE_SOURCE_TABLE if scope.kind == "drive" else MAIL_SOURCE_TABLE,
            worker_id=scope.worker_id,
        )
        if not renewed:
            raise SourceLeaseLost("Native source renewal refused")


async def source_worker_external(
    factory: Callable[[], Awaitable[T]], *, renewal: Callable[[], Awaitable[None]] | None = None
) -> T:
    """No source transaction is held while a provider/extractor/embedder runs.

    Renewal failure cancels and joins the external operation. Cancellation
    joins both tasks; no background renewal can outlive its scope.
    """
    if current_source_worker() is None:
        return await factory()
    await renew_native_source()
    if renewal is not None:
        await renewal()

    async def monitor() -> None:
        while True:
            await asyncio.sleep(_heartbeat_interval())
            await renew_native_source()
            if renewal is not None:
                await renewal()

    async def call() -> T:
        return await factory()

    operation = asyncio.create_task(call(), name="native-source-operation")
    renewal_task = asyncio.create_task(monitor(), name="native-source-renewal")
    try:
        done, _ = await asyncio.wait((operation, renewal_task), return_when=asyncio.FIRST_COMPLETED)
        if renewal_task in done:
            await renewal_task
            raise SourceLeaseLost("Native source renewal stopped")
        return await operation
    finally:
        for task in (operation, renewal_task):
            if not task.done():
                task.cancel()
        for task in (operation, renewal_task):
            with suppress(asyncio.CancelledError, Exception):
                await task
