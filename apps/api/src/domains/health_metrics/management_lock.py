"""Sample writers fence the same owner before rows as confirmed management removal."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.users.models import User
from src.domains.users.repository import UserRepository


async def lock_health_manager(db: AsyncSession, actor_id: UUID) -> None:
    """All destructive health management uses the same fresh active-owner fence."""
    owner = await UserRepository(db).get_by_id_for_preference_update(actor_id)
    if owner is None or not owner.is_active or owner.is_deleted:
        raise AuthorizationError()


async def lock_health_writer(db: AsyncSession, actor_id: UUID) -> None:
    with db.no_autoflush:
        owner = await db.scalar(
            select(User.id)
            .where(User.id == actor_id, User.is_active.is_(True), User.deleted_at.is_(None))
            .with_for_update(read=True, key_share=True)
        )
    if owner is None:
        raise AuthorizationError()
