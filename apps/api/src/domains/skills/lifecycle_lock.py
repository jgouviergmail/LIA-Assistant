"""One account lock serializes live skill directory swaps and deferred removals."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import raise_user_inactive
from src.domains.users.models import User


async def lock_skill_owner(db: AsyncSession, actor_id: UUID) -> None:
    """A late import cannot swap files after its owner became inactive."""
    owner = await db.scalar(
        select(User.id)
        .where(
            User.id == actor_id,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if owner is None:
        raise_user_inactive(actor_id)
