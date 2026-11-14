"""Bounded durable file removal, outside transactions and joined through cancellation."""

import asyncio
from collections.abc import Collection
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.attachments.file_contracts import FileRemovalClaim
from src.domains.attachments.file_paths import owned_relative_path
from src.domains.attachments.file_repository import AttachmentFileRepository
from src.infrastructure.async_utils import finish_owned_task
from src.infrastructure.file_transfer import LocalFileRead
from src.infrastructure.observability.metrics_attachments import attachments_cleanup_deleted_total

logger = structlog.get_logger(__name__)


async def unlink_claim(claim: FileRemovalClaim) -> bool:
    """Remove one exact account file off-loop; an absent path is already complete."""
    try:
        path = await asyncio.to_thread(owned_relative_path, claim.owner_id, claim.file_path)
        if claim.check_identity:
            reader = await LocalFileRead.async_open(path)
            try:
                same = (
                    claim.expected_digest is not None
                    and reader.identity_digest == claim.expected_digest
                )
            finally:
                await reader.close()
            if not same:
                return False
        await asyncio.to_thread(path.unlink, missing_ok=True)
        return True
    except FileNotFoundError:
        return True
    except (OSError, ValueError) as exc:
        logger.warning(
            "attachment_file_remove_failed",
            attachment_id=str(claim.attachment_id),
            error_type=type(exc).__name__,
        )
        return False


async def _remove_owned(db: AsyncSession, claim: FileRemovalClaim) -> bool:
    """Keep the unlink and its explicit SQL result under one owned, joined task."""
    removed = await unlink_claim(claim)
    settled = await AttachmentFileRepository(db).finish_removal(claim, removed=removed)
    await db.commit()
    if removed and settled:
        attachments_cleanup_deleted_total.labels(reason=claim.reason).inc()
    return removed and settled


async def cleanup_files(db: AsyncSession, *, ids: Collection[UUID] | None = None) -> dict[str, int]:
    """Retry exact retired files; never claim an uploader or hold SQL across disk work.

    A failed unlink remains durable. Each sweep attempts a file only once and is
    bounded by settings. A crash after unlink but before acknowledgement is safe:
    the next fenced claimant observes the absent immutable path and settles it.
    """
    repo = AttachmentFileRepository(db)
    wanted = iter(dict.fromkeys(ids)) if ids is not None else None
    attempted: set[UUID] = set()
    deleted, errors = 0, 0
    for _ in range(settings.attachments_cleanup_batch_size):
        file_id = next(wanted, None) if wanted is not None else None
        if wanted is not None and file_id is None:
            break
        before = datetime.now(UTC) - timedelta(seconds=settings.attachments_removal_claim_seconds)
        claim = await repo.claim_removal(before=before, excluded=attempted, attachment_id=file_id)
        await db.commit()
        if claim is None:
            if wanted is None:
                break
            continue
        attempted.add(claim.attachment_id)
        removed = await finish_owned_task(asyncio.create_task(_remove_owned(db, claim)))
        deleted += int(removed)
        errors += int(not removed)
    return {"deleted": deleted, "errors": errors}
