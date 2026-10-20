"""A source erasure revokes hosted archives and in-flight jobs atomically."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.account_export.models import AccountExportJob


async def invalidate_account_exports(db: AsyncSession, owner: UUID) -> None:
    # Preserve the path for the cleanup sweep. Download refuses expired rows
    # immediately, even if the filesystem is temporarily unavailable.
    await db.execute(
        update(AccountExportJob)
        .where(
            AccountExportJob.user_id == owner,
            AccountExportJob.status.in_(("pending", "running", "done")),
        )
        .values(status="expired", error_code="source_erased", expires_at=datetime.now(UTC))
    )
