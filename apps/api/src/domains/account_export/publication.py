"""Short owner-first publication fence shared with source erasure."""

from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.account_export.archive_stream import run_disk_io
from src.domains.account_export.models import AccountExportJob
from src.domains.users.models import User


class ExportInvalidatedError(RuntimeError):
    """The source or account changed while this private archive was building."""


async def publish_archive(
    db: AsyncSession, owner: UUID, job_id: UUID, revision: int, tmp_path: Path, final_path: Path
) -> None:
    actor = await db.scalar(
        select(User)
        .where(User.id == owner)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        actor is None
        or not actor.is_active
        or actor.is_deleted
        or (actor.extraction_revision or 0) != revision
    ):
        raise ExportInvalidatedError("export_invalidated")
    job = await db.scalar(
        select(AccountExportJob)
        .where(AccountExportJob.id == job_id, AccountExportJob.user_id == owner)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if job is None or job.status != "running":
        raise ExportInvalidatedError("export_invalidated")
    # Same filesystem, atomic rename; persist its cleanup pointer in this fence.
    # Each disk call runs in a worker thread that a cancellation waits for (AC-035),
    # so a rename that landed is taken back whenever the fence does not close.
    if await run_disk_io(final_path.exists):
        raise ExportInvalidatedError("export_already_exists")
    try:
        await run_disk_io(tmp_path.replace, final_path)
        job.file_path = str(final_path)
        await db.flush()
    except BaseException:
        await run_disk_io(final_path.unlink, missing_ok=True)
        raise
