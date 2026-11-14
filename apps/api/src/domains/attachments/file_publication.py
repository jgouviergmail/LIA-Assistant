"""One publication protocol for uploads and owned copies, with joined disk work."""

import asyncio
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversation_target import ConversationRef
from src.domains.attachments.file_contracts import FileWriteResult, FileWriteTicket, UploadMetadata
from src.domains.attachments.file_paths import owned_relative_path
from src.domains.attachments.file_repository import AttachmentFileRepository
from src.domains.attachments.models import Attachment
from src.infrastructure.async_utils import finish_owned_task

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class FilePublication:
    """One immutable local write and the metadata committed before it runs."""

    metadata: UploadMetadata
    write: Callable[[Path], FileWriteResult]


async def publish_file(
    db: AsyncSession,
    *,
    owner_id: UUID,
    metadata: UploadMetadata,
    target: ConversationRef | None,
    write: Callable[[Path], FileWriteResult],
) -> Attachment:
    """Commit ownership, join the disk effect, then publish under fresh source authority.

    Args:
        db: The caller's session, with its preceding source reads complete.
        owner_id: Authenticated owner, not derived from a file or discussion id.
        metadata: Validated metadata; the file path is allocated by the repository.
        target: Frozen source at request admission, or a legacy unbound upload.
        write: Synchronous local disk work. It is run off-loop and joined through
            repeated cancellation; cancelling an await cannot stop its thread.

    Returns:
        The committed, ready attachment.

    Raises:
        ExecutionRevoked: Account/source retired or exact writer authority lost.
        Exception: Database or disk failure. A committed writer's row remains a
            cleanup intent once its work has stopped; a crash never implies that.
    """
    return (
        await publish_files(
            db, owner_id=owner_id, files=[FilePublication(metadata, write)], target=target
        )
    )[0]


async def publish_files(
    db: AsyncSession,
    *,
    owner_id: UUID,
    files: Sequence[FilePublication],
    target: ConversationRef | None,
) -> list[Attachment]:
    """Publish one batch atomically; every path is recorded before any disk work."""
    if not files:
        return []
    repo = AttachmentFileRepository(db)
    tickets: list[FileWriteTicket] = []
    try:
        for file in files:
            tickets.append(await repo.stage_upload(owner_id, file.metadata, target))
        await db.commit()
        results = []
        for file, ticket in zip(files, tickets, strict=True):
            results.append(await _write_owned(file, ticket))
        attachments = []
        for ticket, result in zip(tickets, results, strict=True):
            attachments.append(await repo.publish_upload(ticket, result, target))
        await db.commit()
        return attachments
    except Exception, asyncio.CancelledError:
        # No thread can still write after finish_owned_task returns or raises.
        # An unknown process death leaves UPLOADED owned by its exact worker,
        # deliberately ineligible for a timeout-based sweep takeover.
        await finish_owned_task(asyncio.create_task(_abandon(db, repo, tickets)))
        raise


async def _abandon(
    db: AsyncSession, repo: AttachmentFileRepository, tickets: Sequence[FileWriteTicket]
) -> None:
    """Keep every failed path; a successful but unacknowledged publication stays ready."""
    await db.rollback()
    changed = False
    for ticket in tickets:
        changed = await repo.abandon_upload(ticket) or changed
    if changed:
        await db.commit()
    else:
        await db.rollback()


async def _write_owned(file: FilePublication, ticket: FileWriteTicket) -> FileWriteResult:
    """Join one actual disk writer before publishing or retiring its path."""
    logger.info(
        "attachment_write_reserved",
        attachment_id=str(ticket.attachment_id),
        user_id=str(ticket.owner_id),
        worker_id=str(ticket.worker_id),
        process_id=os.getpid(),
    )

    def write() -> FileWriteResult:
        return file.write(owned_relative_path(ticket.owner_id, ticket.file_path))

    return await finish_owned_task(asyncio.create_task(asyncio.to_thread(write)))
