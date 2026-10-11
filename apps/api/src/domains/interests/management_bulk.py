"""Complete owned erasure scopes stream with bounded allocations and stable lock order."""

from collections.abc import AsyncGenerator
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from src.domains.interests.models import UserInterest


async def iter_owned_interests(
    db: AsyncSession, actor_id: UUID, *, for_update: bool = False
) -> AsyncGenerator[UserInterest]:
    query = (
        select(UserInterest)
        .where(UserInterest.user_id == actor_id)
        .order_by(UserInterest.id)
        .options(defer(UserInterest.embedding))
        .execution_options(populate_existing=True, yield_per=200)
    )
    if for_update:
        query = query.with_for_update()
    result = await db.stream_scalars(query)
    try:
        async for row in result:
            yield row
    finally:
        await result.close()
