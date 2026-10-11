"""Stream the complete owned erasure scope with bounded allocations and stable locks."""

from collections.abc import AsyncGenerator
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from src.domains.memories.models import Memory


async def iter_owned_memories(
    db: AsyncSession, actor_id: UUID, *, for_update: bool = False, include_invalidated: bool = True
) -> AsyncGenerator[Memory]:
    """Unlike management pages, GDPR erasure includes superseded historical rows."""
    query = (
        select(Memory)
        .where(Memory.user_id == actor_id)
        .order_by(Memory.id)
        .options(
            defer(Memory.embedding),
            defer(Memory.keyword_embedding),
            defer(Memory.context_biometric),
        )
        .execution_options(populate_existing=True, yield_per=200)
    )
    if not include_invalidated:
        query = query.where(Memory.invalidated_at.is_(None))
    if for_update:
        query = query.with_for_update()
    result = await db.stream_scalars(query)
    try:
        async for row in result:
            yield row
    finally:
        await result.close()
