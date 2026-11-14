"""Owned cleanup execution: no SQL transaction survives an external wait."""

import asyncio
from dataclasses import replace
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import settings
from src.core.constants import CONVERSATION_CLEANUP_PAGE_SIZE
from src.domains.attachments.file_cleanup import cleanup_files
from src.domains.attachments.models import Attachment
from src.domains.conversations.cleanup_contracts import (
    CleanupClaim,
    CleanupPhase,
    RuntimeCleanupPort,
)
from src.domains.conversations.cleanup_repository import CleanupError, ConversationCleanupRepository
from src.infrastructure.async_utils import finish_owned_task

logger = structlog.get_logger(__name__)


async def _stop[T](task: asyncio.Task[T]) -> None:
    """Join an owned child without re-raising its already observed failure."""

    async def join() -> None:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    await finish_owned_task(asyncio.create_task(join()))


class ConversationCleanupRunner:
    """The owner renews on its own sessions and joins all work before returning."""

    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], runtime: RuntimeCleanupPort
    ) -> None:
        """Inject session ownership and native runtime operations at composition."""
        self.sessions = sessions
        self.runtime = runtime

    async def run_one(self, *, operation_id: UUID | None = None) -> bool:
        """Attempt one due operation; false never claims physical completion."""
        async with self.sessions() as db:
            claim = await ConversationCleanupRepository(db).claim(
                lease_seconds=settings.conversation_cleanup_lease_seconds,
                operation_id=operation_id,
            )
            await db.commit()
        if claim is None:
            return False
        return await self._supervise(claim)

    async def _supervise(self, claim: CleanupClaim) -> bool:
        """A lost heartbeat stops subsequent phases and cannot settle a successor."""
        work = asyncio.create_task(self._phases(claim))
        heartbeat = asyncio.create_task(self._heartbeat(claim))
        try:
            done, _ = await asyncio.wait({work, heartbeat}, return_when=asyncio.FIRST_COMPLETED)
            if work in done:
                result = work.result()
                if not result:
                    await self._fail(claim, "cleanup_refused")
                return result
            heartbeat.result()
            await _stop(work)
            logger.warning("conversation_cleanup_claim_lost", operation_id=str(claim.operation_id))
            return False
        except asyncio.CancelledError:
            await _stop(work)
            await finish_owned_task(asyncio.create_task(self._fail(claim, "cleanup_cancelled")))
            raise
        except Exception as exc:
            await _stop(work)
            await self._fail(claim, "cleanup_failed")
            logger.warning(
                "conversation_cleanup_failed",
                operation_id=str(claim.operation_id),
                error_type=type(exc).__name__,
            )
            return False
        finally:
            await _stop(heartbeat)

    async def _heartbeat(self, claim: CleanupClaim) -> None:
        """Never extend an expired owner; every renewal commits independently."""
        while True:
            await asyncio.sleep(settings.conversation_cleanup_lease_seconds / 3)
            async with self.sessions() as db:
                renewed = await ConversationCleanupRepository(db).renew(
                    claim,
                    lease_seconds=settings.conversation_cleanup_lease_seconds,
                )
                await db.commit()
            if not renewed:
                return

    async def _phases(self, claim: CleanupClaim) -> bool:
        """Each next effect requires acknowledgement under the still-current fence."""
        phases = tuple(phase for phase in CleanupPhase if phase != CleanupPhase.COMPLETE)
        for phase in phases[phases.index(claim.phase) :]:
            current = replace(claim, phase=phase)
            async with asyncio.timeout(settings.conversation_cleanup_phase_seconds):
                completed = await self._phase(current)
            if not completed:
                return False
            async with self.sessions() as db:
                advanced = await ConversationCleanupRepository(db).advance(current)
                await db.commit()
            if not advanced:
                return False
        return True

    async def _phase(self, claim: CleanupClaim) -> bool:
        """Native adapters own interpretation of success for their boundary."""
        if claim.phase == CleanupPhase.CHECKPOINT:
            return await self.runtime.purge_checkpoint(claim.target)
        if claim.phase == CleanupPhase.CONTEXT:
            return await self.runtime.purge_tool_context(claim.target)
        if claim.phase == CleanupPhase.PENDING:
            return await self.runtime.purge_pending(claim.target)
        return await self._files(claim)

    async def _files(self, claim: CleanupClaim) -> bool:
        """The file's own durable claim controls unlink; absent rows are already done."""
        batch = min(CONVERSATION_CLEANUP_PAGE_SIZE, settings.attachments_cleanup_batch_size)
        for start in range(0, len(claim.attachment_ids), batch):
            ids = claim.attachment_ids[start : start + batch]
            async with self.sessions() as db:
                result = await cleanup_files(db, ids=ids)
                remaining = await db.scalar(
                    select(Attachment.id).where(Attachment.id.in_(ids)).limit(1)
                )
                await db.commit()
            if result["errors"] or remaining is not None:
                return False
        return True

    async def _fail(self, claim: CleanupClaim, code: CleanupError) -> None:
        """Retain uncertainty and the last acknowledged phase on a short owned session."""
        async with self.sessions() as db:
            await ConversationCleanupRepository(db).fail(
                claim,
                error_code=code,
                max_attempts=settings.conversation_cleanup_max_attempts,
                retry_seconds=settings.conversation_cleanup_retry_seconds,
            )
            await db.commit()
