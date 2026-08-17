"""Agent Plugins repository for database operations (ADR-225)."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.plugins.models import UserPlugin


class UserPluginRepository(BaseRepository[UserPlugin]):
    """Repository for installed-plugin CRUD operations."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, UserPlugin)

    async def get_all_for_user(self, user_id: UUID) -> list[UserPlugin]:
        """Get all installed plugins for a user, ordered by name."""
        stmt = (
            select(UserPlugin).where(UserPlugin.user_id == user_id).order_by(UserPlugin.name.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name_for_user(self, user_id: UUID, name: str) -> UserPlugin | None:
        """Get one installed plugin by its per-user unique name."""
        stmt = select(UserPlugin).where(UserPlugin.user_id == user_id, UserPlugin.name == name)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def count_for_user(self, user_id: UUID) -> int:
        """Count installed plugins for the per-user quota check."""
        stmt = select(func.count(UserPlugin.id)).where(UserPlugin.user_id == user_id)
        result = await self.db.execute(stmt)
        return int(result.scalar_one())
