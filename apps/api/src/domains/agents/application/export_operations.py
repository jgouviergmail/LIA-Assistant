"""Read saved export-job state without queueing or downloading an archive."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.infrastructure.account_exports import AccountExportProjection, get_account_exports


async def read_export_settings(db: AsyncSession, actor_id: UUID) -> AccountExportProjection:
    await require_application_tools(db)
    await load_actor(db, actor_id)
    result = await get_account_exports().read(db, actor_id)
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return result
