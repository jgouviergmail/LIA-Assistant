"""Shared queue command; the source router and confirmed assistant use one writer."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.config import settings
from src.core.constants import RATE_LIMIT_ACCOUNT_EXPORT_PER_MINUTE
from src.core.exceptions import AuthorizationError, raise_invalid_input
from src.domains.account_export.models import AccountExportJob, ExportJobStatus
from src.domains.account_export.queries import project_export_job
from src.domains.account_export.schemas import ExportJobResponse
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.observability.metrics_mfa import account_export_jobs_total

logger = structlog.get_logger(__name__)
rate_limit_export = create_user_rate_limiter(
    action="account_export", max_calls=RATE_LIMIT_ACCOUNT_EXPORT_PER_MINUTE
)


async def queue_account_export(
    db: AsyncSession,
    user: User,
    *,
    job_id: UUID | None = None,
    receipt: PreferenceWriteReceipt | None = None,
    check: Callable[[], Awaitable[None]] | None = None,
) -> ExportJobResponse:
    """Queue once under the existing partial unique index and caller's live checks."""
    if check is not None:
        await _check_export(check)
    if await active_account_export(db, user.id) is not None:
        raise_invalid_input("An export is already in progress for this account")
    if check is not None:
        await _check_export(check)
    job = AccountExportJob(user_id=user.id, **({"id": job_id} if job_id else {}))
    db.add(job)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise_invalid_input("An export is already in progress for this account")
    if receipt is not None:
        receipt.committed = True
    account_export_jobs_total.labels(status="requested").inc()
    logger.info("account_export_requested", user_id=str(user.id), job_id=str(job.id))
    await db.refresh(job)
    return project_export_job(job)


async def active_account_export(db: AsyncSession, actor_id: UUID) -> AccountExportJob | None:
    existing = await db.execute(
        select(AccountExportJob).where(
            AccountExportJob.user_id == actor_id,
            AccountExportJob.status.in_(
                [ExportJobStatus.PENDING.value, ExportJobStatus.RUNNING.value]
            ),
        )
    )
    job: AccountExportJob | None = existing.scalar_one_or_none()
    return job


async def _check_export(check: Callable[[], Awaitable[None]]) -> None:
    if not settings.account_export_enabled:
        raise AuthorizationError(detail={"error_code": "FEATURE_DISABLED"})
    await check()
    if not settings.account_export_enabled:
        raise AuthorizationError(detail={"error_code": "FEATURE_DISABLED"})


async def request_owned_account_export(
    db: AsyncSession,
    actor_id: UUID,
    job_id: UUID,
    origin: ApplicationOrigin | None,
    receipt: PreferenceWriteReceipt,
    *,
    check: Callable[[], Awaitable[None]],
    approved_until: datetime,
) -> ExportJobResponse:
    """The confirmed writer locks authority and rereads live proof before insertion."""
    if origin is None:
        raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})

    async def current() -> None:
        await check()
        actor: User | None = await db.scalar(
            select(User)
            .where(User.id == actor_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if actor is None or not actor.is_active or actor.is_deleted:
            raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
        await check()
        await origin.require_session(
            actor_id, expected_binding=origin.binding_id, recent_step_up=True
        )
        if approved_until.tzinfo is None or datetime.now(UTC) >= approved_until:
            raise AuthorizationError(detail={"error_code": "EXPIRED"})

    await _check_export(current)
    actor = await db.get(User, actor_id)
    if actor is None:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    await rate_limit_export(actor)
    return await queue_account_export(db, actor, job_id=job_id, receipt=receipt, check=current)
