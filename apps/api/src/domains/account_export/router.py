"""Account export endpoints (security program D3).

Mounted only when ``ACCOUNT_EXPORT_ENABLED`` is true. Requesting an export
demands a fresh step-up (the archive contains decrypted personal data);
downloads are authenticated, ownership-scoped, and bounded by the retention
window. Audit stays at counters/ids — never content.
"""

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session, require_recent_step_up
from src.domains.account_export.commands import queue_account_export, rate_limit_export
from src.domains.account_export.downloads import get_owned_download_job
from src.domains.account_export.queries import (
    latest_account_export,
    project_export_job,
)
from src.domains.account_export.schemas import ExportJobResponse
from src.domains.users.models import User
from src.infrastructure.observability.metrics_mfa import account_export_jobs_total

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/account/export", tags=["Account"])

_to_response = project_export_job


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
    return await queue_account_export(db, user)


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
    job = await latest_account_export(db, user.id)
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
    job = await get_owned_download_job(db, user.id, job_id, lock=True)
    assert job.file_path is not None

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
