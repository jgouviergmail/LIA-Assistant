"""Shared catalogue selection boundary for UI and assistant preference writers.

As with timezone propagation, orchestration spans existing bounded contexts and
belongs outside either domain to avoid a users/personalities runtime cycle.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceNotFoundError
from src.domains.personalities.models import Personality


async def require_selectable_personality(
    db: AsyncSession, personality_id: UUID | None, *, lock: bool = False
) -> None:
    if personality_id is None:
        return
    query = select(Personality.id).where(Personality.id == personality_id, Personality.is_active)
    if lock:
        query = query.with_for_update(read=True)
    if await db.scalar(query) != personality_id:
        raise ResourceNotFoundError("personality", personality_id)
