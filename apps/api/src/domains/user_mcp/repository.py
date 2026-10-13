"""
User MCP Server repository for database operations.

Phase: evolution F2.1 — MCP Per-User
Created: 2026-02-28
"""

from typing import Any
from uuid import UUID

from sqlalchemy import func, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, defer

from src.core.exceptions import ResourceNotFoundError
from src.core.repository import BaseRepository
from src.domains.user_mcp.models import UserMCPServer, UserMCPServerStatus
from src.domains.users.models import User


class UserMCPServerRepository(BaseRepository[UserMCPServer]):
    """Repository for user MCP server CRUD operations."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, UserMCPServer)

    async def lock_owner_for_creation(self, user_id: UUID) -> None:
        """All creation paths serialize the final per-account quota/name decision."""
        owner = await self.db.scalar(select(User.id).where(User.id == user_id).with_for_update())
        if owner is None:
            raise ResourceNotFoundError("user", str(user_id))

    async def get_page_for_user(
        self, user_id: UUID, *, server_id: UUID | None, offset: int, limit: int
    ) -> tuple[list[UserMCPServer], int]:
        """One snapshot and predicate owns both the exact total and stable page."""
        base = select(UserMCPServer).where(UserMCPServer.user_id == user_id)
        if server_id is not None:
            base = base.where(UserMCPServer.id == server_id)
        count = select(func.count().label("total")).select_from(base.subquery()).cte("mcp_count")
        page = (
            base.order_by(UserMCPServer.name, UserMCPServer.id)
            .offset(offset)
            .limit(limit)
            .cte("mcp_page")
        )
        server = aliased(UserMCPServer, page)
        statement = (
            select(server, count.c.total)
            .select_from(count.outerjoin(page, true()))
            .execution_options(populate_existing=True)
        )
        rows = (await self.db.execute(statement)).tuples().all()
        return [row for row, _ in rows if row is not None], int(rows[0][1])

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

        The persisted vector envelope (``tool_embeddings_cache``, megabytes of
        JSON per server) is NOT loaded here: every turn used to parse it into
        Python floats for a catalogue that had not changed (ADR-283 amendment
        2026-10-12). It is read alone, by :meth:`get_tool_embeddings_cache`,
        when the per-worker vector cache has no entry for the catalogue.
        """
        stmt = (
            select(UserMCPServer)
            .options(defer(UserMCPServer.tool_embeddings_cache))
            .where(UserMCPServer.user_id == user_id)
            .where(UserMCPServer.is_enabled.is_(True))
            .where(UserMCPServer.status == UserMCPServerStatus.ACTIVE.value)
            .order_by(UserMCPServer.name.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_tool_embeddings_cache(self, server_id: UUID) -> dict[str, Any] | None:
        """The persisted vector envelope of one server, read alone.

        Args:
            server_id: The server whose envelope is wanted.

        Returns:
            The envelope as stored, or None when the row has none (or is gone).
        """
        stmt = select(UserMCPServer.tool_embeddings_cache).where(UserMCPServer.id == server_id)
        envelope: dict[str, Any] | None = await self.db.scalar(stmt)
        return envelope

    async def get_auth_required_for_user(
        self,
        user_id: UUID,
    ) -> list[UserMCPServer]:
        """
        Get enabled MCP servers awaiting re-authentication for a user.

        These servers are invisible to tool registration (which only loads
        ``active`` rows), so this is how the agent context learns that a
        capability is one reconnection away rather than nonexistent
        (2026-09-02 incident: the model asserted "no access" instead).
        """
        stmt = (
            select(UserMCPServer)
            .where(UserMCPServer.user_id == user_id)
            .where(UserMCPServer.is_enabled.is_(True))
            .where(UserMCPServer.status == UserMCPServerStatus.AUTH_REQUIRED.value)
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

    async def get_by_plugin_id(self, plugin_id: UUID) -> list[UserMCPServer]:
        """Get the servers installed by one Agent Plugins package (ADR-225)."""
        stmt = (
            select(UserMCPServer)
            .where(UserMCPServer.plugin_id == plugin_id)
            .order_by(UserMCPServer.name.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
