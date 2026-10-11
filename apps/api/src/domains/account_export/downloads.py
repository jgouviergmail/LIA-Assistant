"""Open only the owned, immutable completed archive selected for a download."""

import hashlib
import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

import anyio
import structlog
from sqlalchemy import Result, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.domains.account_export.models import AccountExportJob
from src.domains.account_export.queries import archive_available
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.account_export_downloads import (
    ExportArchiveRead,
    ExportArchiveSnapshot,
    ExportDownloadCompletionUnknown,
)
from src.infrastructure.observability.metrics_mfa import account_export_jobs_total

logger = structlog.get_logger(__name__)


def _archive_path(job: AccountExportJob) -> Path:
    if job.file_path is None:
        raise ResourceNotFoundError("account_export", str(job.id))
    # The source job retains its path across storage-root changes. The model
    # supplies only an owned job id; the immutable snapshot freezes this path.
    return Path(job.file_path)


def _snapshot(job: AccountExportJob, metadata: os.stat_result) -> ExportArchiveSnapshot:
    if job.expires_at is None or (
        job.file_size_bytes is not None and job.file_size_bytes != metadata.st_size
    ):
        raise ResourceConflictError("account_export", detail={"error_code": "STALE_STATE"})
    identity = (
        job.file_path,
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        job.file_size_bytes,
    )
    return ExportArchiveSnapshot(
        job_id=job.id,
        created_at=job.created_at,
        completed_at=job.completed_at,
        expires_at=job.expires_at,
        file_size_bytes=metadata.st_size,
        archive_digest=hashlib.sha256(repr(identity).encode("utf-8")).hexdigest(),
    )


async def get_owned_download_job(
    db: AsyncSession, actor_id: UUID, job_id: UUID, *, lock: bool = False
) -> AccountExportJob:
    query = (
        select(AccountExportJob)
        .where(AccountExportJob.id == job_id, AccountExportJob.user_id == actor_id)
        .execution_options(populate_existing=True)
    )
    if lock:
        query = query.with_for_update()
    result: Result[tuple[AccountExportJob]] = await db.execute(query)
    job = result.scalar_one_or_none()
    if job is None or not archive_available(job):
        raise ResourceNotFoundError("account_export", str(job_id))
    return job


async def read_owned_archive(
    db: AsyncSession, actor_id: UUID, job_id: UUID
) -> ExportArchiveSnapshot:
    job = await get_owned_download_job(db, actor_id, job_id)
    try:
        # Windows can report different ctime semantics for path stat and fstat.
        # Both selections use the opened descriptor, with no archive bytes read.
        with _archive_path(job).open("rb") as file:
            return _snapshot(job, os.fstat(file.fileno()))
    except OSError, ValueError:
        raise ResourceNotFoundError("account_export", str(job_id)) from None


class _ArchiveReader:
    def __init__(self, file: BinaryIO, snapshot: ExportArchiveSnapshot) -> None:
        self._file, self._snapshot = file, snapshot

    @property
    def snapshot(self) -> ExportArchiveSnapshot:
        return self._snapshot

    async def read_chunk(self) -> bytes:
        # anyio waits for the read before delivering cancellation; close cannot race it.
        return await anyio.to_thread.run_sync(self._file.read, 64 * 1024)

    async def close(self) -> None:
        self._file.close()


async def open_owned_archive(
    db: AsyncSession,
    actor_id: UUID,
    expected: ExportArchiveSnapshot,
    receipt: PreferenceWriteReceipt,
    *,
    check: Callable[[], Awaitable[None]],
    approved_until: datetime,
) -> ExportArchiveRead:
    await check()
    actor: User | None = await db.scalar(
        select(User)
        .where(User.id == actor_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if actor is None or not actor.is_active or actor.is_deleted:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    job = await get_owned_download_job(db, actor_id, expected.job_id, lock=True)
    file: BinaryIO | None = None
    try:
        file = _archive_path(job).open("rb")
        current = _snapshot(job, os.fstat(file.fileno()))
        if current != expected:
            raise ResourceConflictError("account_export", detail={"error_code": "STALE_STATE"})
        await check()
        await _authorize_download(db, actor_id, job, approved_until)
        job.download_count += 1
        await db.flush()
        await check()
        await _authorize_download(db, actor_id, job, approved_until)
        try:
            await db.commit()
        except SQLAlchemyError as exc:
            raise ExportDownloadCompletionUnknown() from exc
        receipt.committed = True
        account_export_jobs_total.labels(status="downloaded").inc()
        logger.info(
            "account_export_download_requested",
            user_id=str(actor_id),
            job_id=str(job.id),
            download_count=job.download_count,
        )
        return _ArchiveReader(file, current)
    except OSError:
        if file is not None:
            file.close()
        raise ResourceNotFoundError("account_export", str(expected.job_id)) from None
    except BaseException:
        if file is not None:
            file.close()
        raise


async def _authorize_download(
    db: AsyncSession, actor_id: UUID, job: AccountExportJob, approved_until: datetime
) -> None:
    actor: User | None = await db.scalar(
        select(User).where(User.id == actor_id).execution_options(populate_existing=True)
    )
    if not settings.account_export_enabled:
        raise AuthorizationError(detail={"error_code": "FEATURE_DISABLED"})
    if actor is None or not actor.is_active or actor.is_deleted:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    now = datetime.now(UTC)
    if (
        approved_until.tzinfo is None
        or approved_until <= now
        or job.expires_at is None
        or job.expires_at <= now
    ):
        raise AuthorizationError(detail={"error_code": "EXPIRED"})
