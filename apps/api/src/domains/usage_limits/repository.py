"""
Usage limits domain repository.

Data access layer for UserUsageLimit with complex JOINs
against users and user_statistics tables.

Phase: evolution — Per-User Usage Limits
Created: 2026-03-21
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import Row, String, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.repository import BaseRepository
from src.domains.auth.models import User
from src.domains.chat.models import UserStatistics
from src.domains.usage_limits.models import UserUsageLimit

logger = structlog.get_logger(__name__)


def _build_user_stats_columns() -> list[Any]:
    """Build the shared SELECT columns for user + limits + stats queries.

    Centralizes the column definitions used by both get_all_with_stats
    and get_user_with_stats to avoid duplication (DRY).

    Returns:
        List of SQLAlchemy column expressions.
    """
    # Include cached tokens to match dashboard calculation
    # (dashboard: cycle_prompt + cycle_completion + cycle_cache)
    cycle_tokens = func.coalesce(
        UserStatistics.cycle_prompt_tokens
        + UserStatistics.cycle_completion_tokens
        + UserStatistics.cycle_cached_tokens,
        0,
    )
    total_tokens = func.coalesce(
        UserStatistics.total_prompt_tokens
        + UserStatistics.total_completion_tokens
        + UserStatistics.total_cached_tokens,
        0,
    )

    return [
        User.id.label("user_id"),
        User.email,
        User.full_name,
        User.is_active,
        User.deleted_at,
        User.created_at,
        # Limits config
        UserUsageLimit.token_limit_per_cycle,
        UserUsageLimit.message_limit_per_cycle,
        UserUsageLimit.cost_limit_per_cycle,
        UserUsageLimit.token_limit_absolute,
        UserUsageLimit.message_limit_absolute,
        UserUsageLimit.cost_limit_absolute,
        UserUsageLimit.is_usage_blocked,
        UserUsageLimit.blocked_reason,
        UserUsageLimit.blocked_at,
        UserUsageLimit.blocked_by,
        # Current usage
        cycle_tokens.label("cycle_tokens"),
        func.coalesce(UserStatistics.cycle_messages, 0).label("cycle_messages"),
        # Cost = LLM cost + Google API cost + Image Generation cost
        func.coalesce(
            UserStatistics.cycle_cost_eur
            + UserStatistics.cycle_google_api_cost_eur
            + UserStatistics.cycle_image_generation_cost_eur,
            Decimal("0"),
        ).label("cycle_cost"),
        total_tokens.label("total_tokens"),
        func.coalesce(UserStatistics.total_messages, 0).label("total_messages"),
        func.coalesce(
            UserStatistics.total_cost_eur
            + UserStatistics.total_google_api_cost_eur
            + UserStatistics.total_image_generation_cost_eur,
            Decimal("0"),
        ).label("total_cost"),
        # Cycle tracking
        UserStatistics.current_cycle_start,
    ]


class UsageLimitRepository(BaseRepository[UserUsageLimit]):
    """Repository for UserUsageLimit database operations.

    Inherits BaseRepository for generic CRUD. Adds domain-specific queries
    with JOINs against users and user_statistics tables.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with database session.

        Args:
            db: SQLAlchemy async session.
        """
        super().__init__(db, UserUsageLimit)

    async def get_by_user_id(self, user_id: UUID) -> UserUsageLimit | None:
        """Get limit configuration for a specific user.

        Args:
            user_id: User UUID.

        Returns:
            UserUsageLimit if found, None otherwise.
        """
        stmt = select(UserUsageLimit).where(UserUsageLimit.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create_for_user(self, user_id: UUID) -> UserUsageLimit:
        """Get existing limit record or create one with default settings.

        Handles race conditions via unique constraint — if a concurrent
        request creates the record first, we fetch it.

        Args:
            user_id: User UUID.

        Returns:
            UserUsageLimit record (existing or newly created).
        """
        existing = await self.get_by_user_id(user_id)
        if existing:
            return existing

        # Create with defaults from settings
        limit = UserUsageLimit(
            user_id=user_id,
            token_limit_per_cycle=settings.default_token_limit_per_cycle,
            message_limit_per_cycle=settings.default_message_limit_per_cycle,
            cost_limit_per_cycle=(
                Decimal(str(settings.default_cost_limit_per_cycle_eur))
                if settings.default_cost_limit_per_cycle_eur is not None
                else None
            ),
            token_limit_absolute=settings.default_token_limit_absolute,
            message_limit_absolute=settings.default_message_limit_absolute,
            cost_limit_absolute=(
                Decimal(str(settings.default_cost_limit_absolute_eur))
                if settings.default_cost_limit_absolute_eur is not None
                else None
            ),
        )

        try:
            async with self.db.begin_nested():
                self.db.add(limit)
                await self.db.flush()
            await self.db.refresh(limit)
            logger.info(
                "usage_limit_record_created",
                user_id=str(user_id),
            )
            return limit
        except Exception:
            # Unique constraint race condition — savepoint rolled back, retry fetch
            existing = await self.get_by_user_id(user_id)
            if existing:
                return existing
            raise

    async def get_all_with_stats(
        self,
        page: int,
        page_size: int,
        search: str | None = None,
        blocked_only: bool = False,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[Row[Any]], int]:
        """Get paginated users with limits and usage stats.

        Single query with LEFT JOINs for efficiency. Returns all data needed
        for AdminUserUsageLimitResponse, including current usage from UserStatistics.

        Args:
            page: Page number (1-based).
            page_size: Items per page.
            search: Optional search query (email or name).
            blocked_only: If True, only return manually blocked users.
            sort_by: Column to sort by (email, is_usage_blocked, created_at).
            sort_order: Sort order (asc or desc).

        Returns:
            Tuple of (rows, total_count).
        """
        base_query = (
            select(*_build_user_stats_columns())
            .outerjoin(UserUsageLimit, UserUsageLimit.user_id == User.id)
            .outerjoin(UserStatistics, UserStatistics.user_id == User.id)
            .where(User.is_verified == True)  # noqa: E712 — SQLAlchemy requires ==
        )

        # Apply filters
        if search:
            search_pattern = f"%{search}%"
            base_query = base_query.where(
                or_(
                    User.email.ilike(search_pattern),
                    User.full_name.cast(String).ilike(search_pattern),
                )
            )

        if blocked_only:
            base_query = base_query.where(UserUsageLimit.is_usage_blocked == True)  # noqa: E712

        # Count total
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        # Apply dynamic sorting
        sort_map = {
            "email": User.email,
            "is_usage_blocked": UserUsageLimit.is_usage_blocked,
            "created_at": User.created_at,
        }
        sort_column = sort_map.get(sort_by, User.created_at)
        if sort_order.lower() == "asc":
            order_clause = sort_column.asc().nulls_last()
        else:
            order_clause = sort_column.desc().nulls_last()

        # Apply pagination and ordering
        paginated_query = (
            base_query.order_by(order_clause).limit(page_size).offset((page - 1) * page_size)
        )

        result = await self.db.execute(paginated_query)
        rows = list(result.all())

        return rows, total

    async def get_user_with_stats(self, user_id: UUID) -> Row[Any] | None:
        """Get a single user with limits and usage stats.

        Args:
            user_id: User UUID.

        Returns:
            Row with user, limits, and stats data, or None if user not found.
        """
        stmt = (
            select(*_build_user_stats_columns())
            .outerjoin(UserUsageLimit, UserUsageLimit.user_id == User.id)
            .outerjoin(UserStatistics, UserStatistics.user_id == User.id)
            .where(User.id == user_id)
        )

        result = await self.db.execute(stmt)
        return result.one_or_none()

    @staticmethod
    def compute_total_pages(total: int, page_size: int) -> int:
        """Compute total number of pages.

        Args:
            total: Total number of items.
            page_size: Items per page.

        Returns:
            Total number of pages (minimum 1).
        """
        return max(1, math.ceil(total / page_size))
