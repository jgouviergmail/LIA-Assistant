"""One account lock serializes live skill directory swaps and deferred removals."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.models import User


async def lock_skill_owner(db: AsyncSession, actor_id: UUID) -> None:
    await db.execute(select(User.id).where(User.id == actor_id).with_for_update())
