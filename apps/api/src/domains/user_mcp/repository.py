"""
User MCP Server repository for database operations.

Phase: evolution F2.1 — MCP Per-User
Created: 2026-02-28
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.user_mcp.models import UserMCPServer, UserMCPServerStatus


class UserMCPServerRepository(BaseRepository[UserMCPServer]):
    """Repository for user MCP server CRUD operations."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, UserMCPServer)

    async def get_all_for_user(
        self,
        user_id: UUID,
        limit: int = 50,
    ) -> list[UserMCPServer]:
        """Get all MCP servers for a user, ordered by name."""
        stmt = (
            select(UserMCPServer)
            .where(UserMCPServer.user_id == user_id)
            .order_by(UserMCPServer.name.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_enabled_active_for_user(
        self,
        user_id: UUID,
    ) -> list[UserMCPServer]:
        """
        Get enabled + active MCP servers for a user.

        Uses the partial index ix_user_mcp_servers_user_enabled for performance.
        This is the hot path called on every chat request.
        """
        stmt = (
            select(UserMCPServer)
            .where(UserMCPServer.user_id == user_id)
            .where(UserMCPServer.is_enabled.is_(True))
            .where(UserMCPServer.status == UserMCPServerStatus.ACTIVE.value)
            .order_by(UserMCPServer.name.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_for_user(self, user_id: UUID) -> int:
        """Count MCP servers for a user (for limit enforcement)."""
        from sqlalchemy import func

        stmt = (
            select(func.count()).select_from(UserMCPServer).where(UserMCPServer.user_id == user_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def get_by_name_for_user(
        self,
        user_id: UUID,
        name: str,
    ) -> UserMCPServer | None:
        """Get a server by name for a specific user (for uniqueness check)."""
        stmt = (
            select(UserMCPServer)
            .where(UserMCPServer.user_id == user_id)
            .where(UserMCPServer.name == name)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
