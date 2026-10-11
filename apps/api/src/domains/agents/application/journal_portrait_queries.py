"""Native observation shares the portrait interface's source-lineage policy."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.journal_queries import require_journal_access
from src.domains.journals.portrait_read import read_managed_portrait
from src.domains.journals.schemas import JournalPortraitResponse


async def read_journal_portrait(db: AsyncSession, actor_id: UUID) -> JournalPortraitResponse:
    actor = await require_journal_access(db, actor_id)
    observed = await read_managed_portrait(db, actor)
    refreshed = await require_journal_access(db, actor_id)
    current = await read_managed_portrait(db, refreshed)
    await require_journal_access(db, actor_id)
    if current != observed:
        raise ValueError("Portrait observation changed while reading; retry")
    return current
