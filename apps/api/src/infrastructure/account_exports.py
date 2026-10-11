"""Injected owner-scoped export boundary; paths and archive data never cross it."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.exceptions import AuthorizationError
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.account_export_downloads import ExportArchiveRead, ExportArchiveSnapshot

ExportJobState = Literal["pending", "running", "done", "failed", "expired"]


class ExportJobResponse(BaseModel):
    id: UUID
    status: ExportJobState
    error_code: str | None = None
    file_size_bytes: int | None = Field(default=None, ge=0)
    created_at: datetime
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    download_available: bool = False


class AccountExportProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    latest: ExportJobResponse | None = None
    download_available: bool = False


class AccountExportGateway(Protocol):
    async def archive_snapshot(
        self, db: AsyncSession, actor_id: UUID, job_id: UUID
    ) -> ExportArchiveSnapshot: ...

    async def open_download(
        self,
        db: AsyncSession,
        actor_id: UUID,
        expected: ExportArchiveSnapshot,
        receipt: PreferenceWriteReceipt,
        *,
        check: Callable[[], Awaitable[None]],
        approved_until: datetime,
    ) -> ExportArchiveRead: ...

    async def read(self, db: AsyncSession, actor_id: UUID) -> AccountExportProjection: ...

    async def has_active(self, db: AsyncSession, actor_id: UUID) -> bool: ...

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
    ) -> ExportJobResponse: ...


_gateway: AccountExportGateway | None = None


def configure_account_exports(gateway: AccountExportGateway | None) -> AccountExportGateway | None:
    global _gateway
    previous, _gateway = _gateway, gateway
    return previous


def get_account_exports() -> AccountExportGateway:
    if _gateway is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    return _gateway
