"""Account export endpoints (security program D3).

Mounted only when ``ACCOUNT_EXPORT_ENABLED`` is true. Requesting an export
demands a fresh step-up (the archive contains decrypted personal data);
downloads are authenticated, ownership-scoped, and bounded by the retention
window. Audit stays at counters/ids — never content.
"""

from datetime import datetime
from pathlib import Path
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import RATE_LIMIT_ACCOUNT_EXPORT_PER_MINUTE
from src.core.dependencies import get_db
from src.core.exceptions import raise_invalid_input, raise_not_found_or_unauthorized
from src.core.session_dependencies import get_current_active_session, require_recent_step_up
from src.domains.account_export.models import AccountExportJob, ExportJobStatus
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.users.models import User
from src.infrastructure.observability.metrics_mfa import account_export_jobs_total

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/account/export", tags=["Account"])

rate_limit_export = create_user_rate_limiter(
    action="account_export",
    max_calls=RATE_LIMIT_ACCOUNT_EXPORT_PER_MINUTE,
)


class ExportJobResponse(BaseModel):
    """Export job state for the Security settings UI."""

    id: UUID = Field(..., description="Job id")
    status: str = Field(..., description="pending | running | done | failed | expired")
    error_code: str | None = Field(default=None, description="Failure classification")
    file_size_bytes: int | None = Field(default=None, description="Archive size when done")
    created_at: datetime = Field(..., description="Request timestamp")
    completed_at: datetime | None = Field(default=None, description="Build end timestamp")
    expires_at: datetime | None = Field(default=None, description="Download deadline")


def _to_response(job: AccountExportJob) -> ExportJobResponse:
    return ExportJobResponse(
        id=job.id,
        status=job.status,
        error_code=job.error_code,
        file_size_bytes=job.file_size_bytes,
        created_at=job.created_at,
        completed_at=job.completed_at,
        expires_at=job.expires_at,
    )


@router.post(
    "",
    response_model=ExportJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Request a full account export (step-up required)",
    description="Queue an asynchronous full-account export. One job at a time per "
    "account; a push notification fires when the archive is ready.",
)
async def request_export(
    user: User = Depends(require_recent_step_up),
    db: AsyncSession = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_export),
) -> ExportJobResponse:
    """Queue an export job (409-equivalent 400 when one is already active)."""
    existing = await db.execute(
        select(AccountExportJob).where(
            AccountExportJob.user_id == user.id,
            AccountExportJob.status.in_(
                [ExportJobStatus.PENDING.value, ExportJobStatus.RUNNING.value]
            ),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise_invalid_input("An export is already in progress for this account")

    job = AccountExportJob(user_id=user.id)
    db.add(job)
    try:
        await db.commit()
    except IntegrityError:
        # Concurrent request lost the race against the partial unique index
        # (one non-terminal job per user) — same answer as the pre-check.
        await db.rollback()
        raise_invalid_input("An export is already in progress for this account")
    await db.refresh(job)

    account_export_jobs_total.labels(status="requested").inc()
    logger.info("account_export_requested", user_id=str(user.id), job_id=str(job.id))
    return _to_response(job)


@router.get(
    "/latest",
    response_model=ExportJobResponse | None,
    summary="Latest export job state",
)
async def latest_export(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ExportJobResponse | None:
    """Return the most recent export job of the account, if any."""
    result = await db.execute(
        select(AccountExportJob)
        .where(AccountExportJob.user_id == user.id)
        .order_by(AccountExportJob.created_at.desc())
        .limit(1)
    )
    job = result.scalar_one_or_none()
    return _to_response(job) if job else None


@router.get(
    "/{job_id}/download",
    summary="Download a completed export archive",
    description="Authenticated, ownership-scoped download. 404 when unknown, not "
    "owned, not done, or past the retention window.",
    response_class=FileResponse,
)
async def download_export(
    job_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Serve the archive (single audit counter, never content in logs)."""
    result = await db.execute(
        select(AccountExportJob).where(
            AccountExportJob.id == job_id,
            AccountExportJob.user_id == user.id,
        )
    )
    job = result.scalar_one_or_none()
    if (
        job is None
        or job.status != ExportJobStatus.DONE.value
        or job.file_path is None
        or not Path(job.file_path).is_file()
    ):
        raise_not_found_or_unauthorized("account_export", job_id)

    job.download_count += 1
    await db.commit()

    account_export_jobs_total.labels(status="downloaded").inc()
    logger.info(
        "account_export_downloaded",
        user_id=str(user.id),
        job_id=str(job_id),
        download_count=job.download_count,
    )
    return FileResponse(
        job.file_path,
        media_type="application/zip",
        filename="lia-account-export.zip",
    )
