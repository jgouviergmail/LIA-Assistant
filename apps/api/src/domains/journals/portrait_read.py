"""Read the portrait the management interface is currently allowed to expose.

The words are served whenever the account may read them; whether their
evidence still stands is a FLAG (``stale``), never a reason to hide them
(2026-10-12, ADR-269's doctrine).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.journals.lifecycle import portrait_is_current
from src.domains.journals.schemas import JournalPortraitResponse, provenance_of
from src.domains.users.models import User


async def read_managed_portrait(db: AsyncSession, actor: User) -> JournalPortraitResponse:
    current = await db.scalar(
        select(User).where(User.id == actor.id).execution_options(populate_existing=True)
    )
    if (
        current is None
        or not current.is_active
        or current.deleted_at is not None
        or not current.journals_enabled
        or not (current.journal_portrait_full or current.journal_portrait_brief)
    ):
        return JournalPortraitResponse()
    return JournalPortraitResponse(
        full=current.journal_portrait_full,
        brief=current.journal_portrait_brief,
        compiled_at=current.journal_portrait_compiled_at,
        sources=provenance_of(current.journal_portrait_sources),
        stale=not await portrait_is_current(db, current),
    )
