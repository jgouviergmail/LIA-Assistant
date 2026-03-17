"""
Sub-Agents repository.

Domain-specific queries extending BaseRepository[SubAgent].
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.sub_agents.models import SubAgent, SubAgentStatus


class SubAgentRepository(BaseRepository[SubAgent]):
    """Repository for sub-agent CRUD and domain-specific queries."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, SubAgent)

    async def get_all_for_user(
        self,
        user_id: UUID,
        include_disabled: bool = False,
    ) -> list[SubAgent]:
        """Get all sub-agents for a user, ordered by name."""
        stmt = select(SubAgent).where(SubAgent.user_id == user_id).order_by(SubAgent.name.asc())
        if not include_disabled:
            stmt = stmt.where(SubAgent.is_enabled.is_(True))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name_for_user(
        self,
        user_id: UUID,
        name: str,
    ) -> SubAgent | None:
        """Get a sub-agent by name for a specific user."""
        stmt = select(SubAgent).where(SubAgent.user_id == user_id).where(SubAgent.name == name)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def count_for_user(self, user_id: UUID) -> int:
        """Count sub-agents for a user (for limit enforcement)."""
        stmt = select(func.count()).select_from(SubAgent).where(SubAgent.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def get_stale_executing(
        self,
        timeout_margin_seconds: int = 60,
    ) -> list[SubAgent]:
        """Get sub-agents stuck in 'executing' status beyond their timeout + margin.

        Uses SQL-side timestamp arithmetic to push filtering to the database.
        Used by the stale recovery job to reset zombie sub-agents.
        """
        # PostgreSQL: last_executed_at + (timeout + margin) seconds < now()
        # Using cast to interval for per-row dynamic timeout
        from sqlalchemy import cast, literal_column
        from sqlalchemy.types import Interval

        timeout_expr = cast(
            (SubAgent.timeout_seconds + timeout_margin_seconds)
            * literal_column("'1 second'::interval"),
            Interval(),
        )

        stmt = (
            select(SubAgent)
            .where(SubAgent.status == SubAgentStatus.EXECUTING.value)
            .where(SubAgent.last_executed_at.isnot(None))
            .where(SubAgent.last_executed_at + timeout_expr < func.now())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
