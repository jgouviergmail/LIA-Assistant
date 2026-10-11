"""Bind export source queries after startup, with fresh owner authority."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.exceptions import AuthorizationError
from src.domains.account_export.commands import active_account_export, request_owned_account_export
from src.domains.account_export.downloads import open_owned_archive, read_owned_archive
from src.domains.account_export.queries import read_account_export
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.account_export_downloads import ExportArchiveRead, ExportArchiveSnapshot
from src.infrastructure.account_exports import AccountExportProjection, ExportJobResponse


class SavedAccountExports:
    async def archive_snapshot(
        self, db: AsyncSession, actor_id: UUID, job_id: UUID
    ) -> ExportArchiveSnapshot:
        await self._authorize(db, actor_id)
        snapshot = await read_owned_archive(db, actor_id, job_id)
        await self._authorize(db, actor_id)
        return snapshot

    async def open_download(
        self,
        db: AsyncSession,
        actor_id: UUID,
        expected: ExportArchiveSnapshot,
        receipt: PreferenceWriteReceipt,
        *,
        check: Callable[[], Awaitable[None]],
        approved_until: datetime,
    ) -> ExportArchiveRead:
        return await open_owned_archive(
            db, actor_id, expected, receipt, check=check, approved_until=approved_until
        )

    async def read(self, db: AsyncSession, actor_id: UUID) -> AccountExportProjection:
        await self._authorize(db, actor_id)
        return await read_account_export(db, actor_id)

    async def has_active(self, db: AsyncSession, actor_id: UUID) -> bool:
        await self._authorize(db, actor_id)
        return await active_account_export(db, actor_id) is not None

    async def request(
        self,
        db: AsyncSession,
        actor_id: UUID,
        job_id: UUID,
        origin: ApplicationOrigin | None,
        receipt: PreferenceWriteReceipt,
        *,
        check: Callable[[], Awaitable[None]],
        approved_until: datetime,
    ) -> ExportJobResponse:
        return await request_owned_account_export(
            db,
            actor_id,
            job_id,
            origin,
            receipt,
            check=check,
            approved_until=approved_until,
        )

    async def _authorize(self, db: AsyncSession, actor_id: UUID) -> None:
        actor: User | None = await db.scalar(
            select(User).where(User.id == actor_id).execution_options(populate_existing=True)
        )
        if actor is None or not actor.is_active or actor.is_deleted:
            raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
