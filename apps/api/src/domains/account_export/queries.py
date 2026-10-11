"""Shared owner-scoped export state and retention checks, without starting or downloading jobs."""

from datetime import UTC, datetime
from pathlib import Path
from typing import get_args
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.account_export.models import AccountExportJob, ExportJobStatus
from src.domains.account_export.schemas import AccountExportProjection, ExportJobResponse
from src.infrastructure.account_exports import ExportJobState


def assert_export_projection_coverage() -> None:
    if set(get_args(ExportJobState)) != {status.value for status in ExportJobStatus}:
        raise AssertionError("New export states require explicit native projection review")
    if set(ExportJobResponse.model_fields) != {
        "id",
        "status",
        "error_code",
        "file_size_bytes",
        "created_at",
        "completed_at",
        "expires_at",
        "download_available",
    }:
        raise AssertionError("New export fields require explicit native projection review")


assert_export_projection_coverage()


def archive_available(job: AccountExportJob, *, now: datetime | None = None) -> bool:
    observed = now or datetime.now(UTC)
    if (
        job.status != ExportJobStatus.DONE.value
        or job.expires_at is None
        or job.expires_at.tzinfo is None
    ):
        return False
    if job.expires_at <= observed or job.file_path is None:
        return False
    try:
        return Path(job.file_path).is_file()
    except OSError, ValueError:
        return False


def project_export_job(job: AccountExportJob) -> ExportJobResponse:
    return ExportJobResponse(
        id=job.id,
        status=job.status,
        error_code=job.error_code,
        file_size_bytes=job.file_size_bytes,
        created_at=job.created_at,
        completed_at=job.completed_at,
        expires_at=job.expires_at,
        download_available=archive_available(job),
    )


async def latest_account_export(db: AsyncSession, actor_id: UUID) -> AccountExportJob | None:
    job: AccountExportJob | None = await db.scalar(
        select(AccountExportJob)
        .where(AccountExportJob.user_id == actor_id)
        .order_by(AccountExportJob.created_at.desc(), AccountExportJob.id.desc())
        .limit(1)
    )
    return job


async def read_account_export(db: AsyncSession, actor_id: UUID) -> AccountExportProjection:
    if not settings.account_export_enabled:
        return AccountExportProjection(enabled=False)
    job = await latest_account_export(db, actor_id)
    latest = project_export_job(job) if job else None
    return AccountExportProjection(
        enabled=True,
        latest=latest,
        download_available=latest.download_available if latest else False,
    )
