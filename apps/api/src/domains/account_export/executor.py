"""Durable export executor (security program D3, arbitration A6).

Interval job (leader-elected) consuming ``account_export_jobs`` with
``FOR UPDATE SKIP LOCKED`` — one build at a time (RPi-class hardware),
crash-safe: a RUNNING row older than the stale threshold is failed
(``crashed``) so the user can simply re-request. The same tick sweeps
expired archives (file deleted, row flipped to EXPIRED).
"""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog
from sqlalchemy import select, update

from src.core.config import settings
from src.core.i18n import normalize_language
from src.core.i18n_api_messages import APIMessages
from src.domains.account_export.builder import ExportTooLargeError, build_export_archive
from src.domains.account_export.models import AccountExportJob, ExportJobStatus
from src.domains.notifications.service import FCMNotificationService
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)


async def process_account_exports() -> None:
    """One executor tick: fail stale runs, sweep expired, build one job."""
    await _fail_stale_running()
    await _sweep_expired()
    await _build_next_pending()


async def _fail_stale_running() -> None:
    """A RUNNING job older than the threshold crashed with its process."""
    threshold = datetime.now(UTC) - timedelta(minutes=settings.account_export_stale_running_minutes)
    async with get_db_context() as db:
        result = await db.execute(
            update(AccountExportJob)
            .where(
                AccountExportJob.status == ExportJobStatus.RUNNING.value,
                AccountExportJob.started_at < threshold,
            )
            .values(
                status=ExportJobStatus.FAILED.value,
                error_code="crashed",
                completed_at=datetime.now(UTC),
            )
        )
        await db.commit()
        if result.rowcount:  # type: ignore[attr-defined]
            logger.warning("account_export_stale_runs_failed", count=result.rowcount)  # type: ignore[attr-defined]


async def _sweep_expired() -> None:
    """Delete archives past their retention window; flip rows to EXPIRED."""
    now = datetime.now(UTC)
    async with get_db_context() as db:
        result = await db.execute(
            select(AccountExportJob).where(
                AccountExportJob.status == ExportJobStatus.DONE.value,
                AccountExportJob.expires_at < now,
            )
        )
        for job in result.scalars().all():
            if job.file_path:
                Path(job.file_path).unlink(missing_ok=True)
            job.status = ExportJobStatus.EXPIRED.value
            job.file_path = None
            logger.info(
                "account_export_expired",
                job_id=str(job.id),
                user_id=str(job.user_id),
            )
        await db.commit()


async def _build_next_pending() -> None:
    """Claim and build ONE pending job (SKIP LOCKED, atomic transition)."""
    async with get_db_context() as db:
        result = await db.execute(
            select(AccountExportJob)
            .where(AccountExportJob.status == ExportJobStatus.PENDING.value)
            .order_by(AccountExportJob.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job = result.scalar_one_or_none()
        if job is None:
            return
        job.status = ExportJobStatus.RUNNING.value
        job.started_at = datetime.now(UTC)
        job_id, user_id = job.id, job.user_id
        await db.commit()

    try:
        archive_path, size = await build_export_archive(user_id, job_id)
        await _finish_job(
            job_id,
            status=ExportJobStatus.DONE.value,
            file_path=str(archive_path),
            file_size_bytes=size,
        )
        await _notify_ready(user_id)
    except ExportTooLargeError as exc:
        logger.warning("account_export_too_large", job_id=str(job_id), error=str(exc))
        await _finish_job(
            job_id, status=ExportJobStatus.FAILED.value, error_code="export_too_large"
        )
    except Exception as exc:
        logger.exception("account_export_build_failed", job_id=str(job_id), error=str(exc))
        await _finish_job(job_id, status=ExportJobStatus.FAILED.value, error_code="build_failed")


async def _finish_job(
    job_id: uuid.UUID,
    status: str,
    file_path: str | None = None,
    file_size_bytes: int | None = None,
    error_code: str | None = None,
) -> None:
    """Persist the terminal state of a build."""
    now = datetime.now(UTC)
    expires = (
        now + timedelta(hours=settings.account_export_retention_hours)
        if status == ExportJobStatus.DONE.value
        else None
    )
    async with get_db_context() as db:
        await db.execute(
            update(AccountExportJob)
            .where(AccountExportJob.id == job_id)
            .values(
                status=status,
                file_path=file_path,
                file_size_bytes=file_size_bytes,
                error_code=error_code,
                completed_at=now,
                expires_at=expires,
            )
        )
        await db.commit()


async def _notify_ready(user_id: uuid.UUID) -> None:
    """Best-effort FCM 'your export is ready' push (localized)."""
    try:
        async with get_db_context() as db:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user is None:
                return
            language = normalize_language(user.language)
            service = FCMNotificationService(db)
            await service.send_to_user(
                user_id=user.id,
                title=APIMessages.export_ready_title(language),
                body=APIMessages.export_ready_body(language),
                data={"kind": "account_export_ready"},
            )
    except Exception as exc:
        logger.warning("account_export_notify_failed", user_id=str(user_id), error=str(exc))
