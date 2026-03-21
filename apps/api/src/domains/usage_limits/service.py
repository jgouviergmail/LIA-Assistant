"""
Usage limits domain service.

Core business logic for per-user usage limit enforcement and management.
Contains both static methods (autonomous, for enforcement checks) and
instance methods (DB-bound, for admin CRUD operations).

Phase: evolution — Per-User Usage Limits
Created: 2026-03-21
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, NamedTuple
from uuid import UUID

import structlog
from dateutil.relativedelta import relativedelta
from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    REDIS_KEY_USAGE_LIMIT_PREFIX,
    USAGE_LIMIT_CRITICAL_THRESHOLD_PCT,
    USAGE_LIMIT_WARNING_THRESHOLD_PCT,
)
from src.domains.usage_limits.models import UserUsageLimit
from src.domains.usage_limits.repository import UsageLimitRepository
from src.domains.usage_limits.schemas import (
    AdminUserUsageLimitListResponse,
    AdminUserUsageLimitResponse,
    LimitDetail,
    UsageBlockUpdate,
    UsageLimitStatus,
    UsageLimitUpdate,
    UserUsageLimitResponse,
)
from src.infrastructure.observability.metrics_usage_limits import (
    usage_limit_check_total,
)

logger = structlog.get_logger(__name__)


class UsageLimitCheckResult(NamedTuple):
    """Result of a usage limit check."""

    allowed: bool
    status: UsageLimitStatus
    blocked_reason: str | None
    exceeded_limit: str | None


class UsageLimitService:
    """Service for usage limit enforcement and management.

    Architecture:
        - Static methods: autonomous, manage own Redis/DB access, for enforcement checks.
        - Instance methods: receive AsyncSession, for admin CRUD operations.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with database session.

        Args:
            db: SQLAlchemy async session.
        """
        self.db = db
        self.repo = UsageLimitRepository(db)

    # ========================================================================
    # Static enforcement methods (autonomous, no self.db needed)
    # ========================================================================

    @staticmethod
    async def check_user_allowed(user_id: UUID) -> UsageLimitCheckResult:
        """Check if a user is allowed to perform LLM operations.

        Autonomous method that manages its own Redis cache and DB access.
        Callable from any context (router, service, scheduler, callback).

        Flow:
            1. Check Redis cache (key: usage_limit:{user_id})
            2. Cache hit → return deserialized result
            3. Cache miss → open DB session, JOIN limits + stats + user
            4. Detect stale cycle data
            5. Compute status via _compute_status()
            6. Cache result in Redis
            7. Redis down → fallback to DB; DB down → fail-open (allow)

        Args:
            user_id: User UUID to check.

        Returns:
            UsageLimitCheckResult with allowed flag and status details.
        """
        if not getattr(settings, "usage_limits_enabled", False):
            return UsageLimitCheckResult(
                allowed=True,
                status=UsageLimitStatus.OK,
                blocked_reason=None,
                exceeded_limit=None,
            )

        cache_key = f"{REDIS_KEY_USAGE_LIMIT_PREFIX}{user_id}"

        # 1. Try Redis cache
        try:
            from src.infrastructure.cache.redis import get_redis_cache
            from src.infrastructure.cache.redis_helpers import cache_get_json

            redis = await get_redis_cache()
            cached = await cache_get_json(redis, cache_key)
            if cached:
                result = UsageLimitCheckResult(
                    allowed=cached["allowed"],
                    status=UsageLimitStatus(cached["status"]),
                    blocked_reason=cached.get("blocked_reason"),
                    exceeded_limit=cached.get("exceeded_limit"),
                )
                usage_limit_check_total.labels(result=result.status.value).inc()
                return result
        except Exception as e:
            logger.warning(
                "usage_limit_cache_read_failed",
                user_id=str(user_id),
                error=str(e),
            )
            redis = None

        # 2. Cache miss → query DB
        try:
            from src.infrastructure.database.session import get_db_context

            async with get_db_context() as db:
                repo = UsageLimitRepository(db)
                row = await repo.get_user_with_stats(user_id)

                if row is None:
                    # User not found — allow (no limits)
                    result = UsageLimitCheckResult(
                        allowed=True,
                        status=UsageLimitStatus.OK,
                        blocked_reason=None,
                        exceeded_limit=None,
                    )
                elif not UsageLimitService._has_limit_record(row):
                    # No limit record (LEFT JOIN all NULLs) — allow (unlimited)
                    result = UsageLimitCheckResult(
                        allowed=True,
                        status=UsageLimitStatus.OK,
                        blocked_reason=None,
                        exceeded_limit=None,
                    )
                else:
                    cycle_is_stale = UsageLimitService._is_cycle_stale(
                        stats_cycle_start=row.current_cycle_start,
                        user_created_at=row.created_at,
                    )
                    result = UsageLimitService._check_from_row(row, cycle_is_stale)

        except Exception as e:
            # DB down → fail-open (allow)
            logger.error(
                "usage_limit_db_check_failed_allowing",
                user_id=str(user_id),
                error=str(e),
                error_type=type(e).__name__,
            )
            return UsageLimitCheckResult(
                allowed=True,
                status=UsageLimitStatus.OK,
                blocked_reason=None,
                exceeded_limit=None,
            )

        # 3. Cache result
        try:
            if redis:
                from src.infrastructure.cache.redis_helpers import cache_set_json

                await cache_set_json(
                    redis,
                    cache_key,
                    {
                        "allowed": result.allowed,
                        "status": result.status.value,
                        "blocked_reason": result.blocked_reason,
                        "exceeded_limit": result.exceeded_limit,
                    },
                    ttl_seconds=settings.usage_limit_cache_ttl_seconds,
                )
        except Exception as e:
            logger.warning(
                "usage_limit_cache_write_failed",
                user_id=str(user_id),
                error=str(e),
            )

        usage_limit_check_total.labels(result=result.status.value).inc()
        return result

    @staticmethod
    async def invalidate_cache_static(user_id: UUID) -> None:
        """Invalidate Redis cache for a user's usage limit check.

        Callable without a service instance (for hooks in TrackingContext).

        Args:
            user_id: User UUID whose cache should be invalidated.
        """
        try:
            from src.infrastructure.cache.redis import get_redis_cache

            redis = await get_redis_cache()
            cache_key = f"{REDIS_KEY_USAGE_LIMIT_PREFIX}{user_id}"
            await redis.delete(cache_key)
        except Exception as e:
            logger.warning(
                "usage_limit_cache_invalidation_failed",
                user_id=str(user_id),
                error=str(e),
            )

    @staticmethod
    def _has_limit_record(row: Row[Any]) -> bool:
        """Check if a LEFT JOIN row has an actual user_usage_limits record.

        When the LEFT JOIN produces no match, all limit columns are NULL.
        We detect the presence of a record by checking is_usage_blocked,
        which has server_default='false' — it's never NULL if the record exists.

        Args:
            row: SQLAlchemy Row from get_user_with_stats().

        Returns:
            True if a UserUsageLimit record exists for this user.
        """
        return row.is_usage_blocked is not None

    @staticmethod
    def _check_from_row(row: Row[Any], cycle_is_stale: bool) -> UsageLimitCheckResult:
        """Compute check result from a repository row with stale cycle handling.

        Extracts all values from the row and delegates to _compute_status.
        Centralizes the row → kwargs extraction pattern (DRY).

        Args:
            row: SQLAlchemy Row from get_user_with_stats/get_all_with_stats.
            cycle_is_stale: Whether cycle data should be treated as 0.

        Returns:
            UsageLimitCheckResult.
        """
        return UsageLimitService._compute_status(
            is_usage_blocked=row.is_usage_blocked or False,
            blocked_reason=row.blocked_reason,
            token_limit_per_cycle=row.token_limit_per_cycle,
            message_limit_per_cycle=row.message_limit_per_cycle,
            cost_limit_per_cycle=row.cost_limit_per_cycle,
            token_limit_absolute=row.token_limit_absolute,
            message_limit_absolute=row.message_limit_absolute,
            cost_limit_absolute=row.cost_limit_absolute,
            cycle_tokens=0 if cycle_is_stale else row.cycle_tokens,
            cycle_messages=0 if cycle_is_stale else row.cycle_messages,
            cycle_cost=Decimal("0") if cycle_is_stale else row.cycle_cost,
            total_tokens=row.total_tokens,
            total_messages=row.total_messages,
            total_cost=row.total_cost,
        )

    @staticmethod
    def _is_cycle_stale(
        stats_cycle_start: datetime | None,
        user_created_at: datetime,
    ) -> bool:
        """Check if UserStatistics cycle data is from a previous cycle.

        Problem: if a user hasn't sent a message since the cycle rollover,
        UserStatistics.cycle_* still contains old cycle data (reset only happens
        in StatisticsService.reset_cycle_if_needed on next message).

        Solution: compare stats.current_cycle_start with the theoretical
        current cycle start calculated from user.created_at.

        Args:
            stats_cycle_start: current_cycle_start from UserStatistics (may be None).
            user_created_at: User signup timestamp for cycle calculation.

        Returns:
            True if cycle data is stale (should treat cycle values as 0).
        """
        if stats_cycle_start is None:
            return True  # No stats yet → treat as new cycle

        from src.domains.chat.service import StatisticsService

        current_cycle_start = StatisticsService.calculate_cycle_start(user_created_at)
        return stats_cycle_start < current_cycle_start

    @staticmethod
    def _compute_status(
        *,
        is_usage_blocked: bool,
        blocked_reason: str | None,
        token_limit_per_cycle: int | None,
        message_limit_per_cycle: int | None,
        cost_limit_per_cycle: Decimal | None,
        token_limit_absolute: int | None,
        message_limit_absolute: int | None,
        cost_limit_absolute: Decimal | None,
        cycle_tokens: int,
        cycle_messages: int,
        cycle_cost: Decimal,
        total_tokens: int,
        total_messages: int,
        total_cost: Decimal,
    ) -> UsageLimitCheckResult:
        """Compute usage limit check result from raw data.

        Pure function — no side effects, no DB/Redis access.

        Args:
            is_usage_blocked: Admin manual block flag.
            blocked_reason: Reason for manual block.
            token_limit_per_cycle: Token limit per cycle (None = unlimited).
            message_limit_per_cycle: Message limit per cycle (None = unlimited).
            cost_limit_per_cycle: Cost limit per cycle (None = unlimited).
            token_limit_absolute: Absolute token limit (None = unlimited).
            message_limit_absolute: Absolute message limit (None = unlimited).
            cost_limit_absolute: Absolute cost limit (None = unlimited).
            cycle_tokens: Current cycle token usage.
            cycle_messages: Current cycle message count.
            cycle_cost: Current cycle cost (EUR).
            total_tokens: Lifetime token usage.
            total_messages: Lifetime message count.
            total_cost: Lifetime cost (EUR).

        Returns:
            UsageLimitCheckResult with allowed, status, reason, and exceeded limit.
        """
        # 1. Manual block check
        if is_usage_blocked:
            return UsageLimitCheckResult(
                allowed=False,
                status=UsageLimitStatus.BLOCKED_MANUAL,
                blocked_reason=blocked_reason or "Manually blocked by administrator",
                exceeded_limit="manual_block",
            )

        # 2. Check each limit dimension
        checks: list[tuple[str, float, float | None]] = [
            (
                "cycle_tokens",
                float(cycle_tokens),
                float(token_limit_per_cycle) if token_limit_per_cycle is not None else None,
            ),
            (
                "cycle_messages",
                float(cycle_messages),
                float(message_limit_per_cycle) if message_limit_per_cycle is not None else None,
            ),
            (
                "cycle_cost",
                float(cycle_cost),
                float(cost_limit_per_cycle) if cost_limit_per_cycle is not None else None,
            ),
            (
                "absolute_tokens",
                float(total_tokens),
                float(token_limit_absolute) if token_limit_absolute is not None else None,
            ),
            (
                "absolute_messages",
                float(total_messages),
                float(message_limit_absolute) if message_limit_absolute is not None else None,
            ),
            (
                "absolute_cost",
                float(total_cost),
                float(cost_limit_absolute) if cost_limit_absolute is not None else None,
            ),
        ]

        max_pct: float = 0.0

        for name, current, limit_val in checks:
            if limit_val is None:
                continue  # Unlimited — skip

            if current >= limit_val:
                return UsageLimitCheckResult(
                    allowed=False,
                    status=UsageLimitStatus.BLOCKED_LIMIT,
                    blocked_reason=f"Usage limit exceeded: {name}",
                    exceeded_limit=name,
                )

            if limit_val > 0:
                pct = (current / limit_val) * 100
                max_pct = max(max_pct, pct)

        # 3. Warning/critical thresholds
        if max_pct >= USAGE_LIMIT_CRITICAL_THRESHOLD_PCT:
            status = UsageLimitStatus.CRITICAL
        elif max_pct >= USAGE_LIMIT_WARNING_THRESHOLD_PCT:
            status = UsageLimitStatus.WARNING
        else:
            status = UsageLimitStatus.OK

        return UsageLimitCheckResult(
            allowed=True,
            status=status,
            blocked_reason=None,
            exceeded_limit=None,
        )

    # ========================================================================
    # Instance methods (DB-bound, for admin CRUD and user-facing endpoints)
    # ========================================================================

    async def get_user_limits_with_usage(
        self,
        user_id: UUID,
        user_created_at: datetime,
    ) -> UserUsageLimitResponse:
        """Get formatted limits and usage for the user-facing /me endpoint.

        Args:
            user_id: User UUID.
            user_created_at: User signup timestamp for cycle calculation.

        Returns:
            UserUsageLimitResponse with all limit dimensions and cycle info.
        """
        from src.domains.chat.service import StatisticsService

        row = await self.repo.get_user_with_stats(user_id)

        cycle_start = StatisticsService.calculate_cycle_start(user_created_at)
        cycle_end = cycle_start + relativedelta(months=1)

        if row is None or not self._has_limit_record(row):
            # No limit record — all unlimited
            unlimited_detail = LimitDetail(current=0, limit=None, usage_pct=None, exceeded=False)
            return UserUsageLimitResponse(
                status=UsageLimitStatus.OK,
                is_blocked=False,
                blocked_reason=None,
                cycle_tokens=unlimited_detail,
                cycle_messages=unlimited_detail,
                cycle_cost=unlimited_detail,
                absolute_tokens=unlimited_detail,
                absolute_messages=unlimited_detail,
                absolute_cost=unlimited_detail,
                cycle_start=cycle_start,
                cycle_end=cycle_end,
            )

        cycle_is_stale = self._is_cycle_stale(row.current_cycle_start, user_created_at)
        c_tokens = 0 if cycle_is_stale else row.cycle_tokens
        c_messages = 0 if cycle_is_stale else row.cycle_messages
        c_cost = Decimal("0") if cycle_is_stale else row.cycle_cost

        check = self._check_from_row(row, cycle_is_stale)

        return UserUsageLimitResponse(
            status=check.status,
            is_blocked=not check.allowed,
            blocked_reason=check.blocked_reason,
            cycle_tokens=self._build_limit_detail(c_tokens, row.token_limit_per_cycle),
            cycle_messages=self._build_limit_detail(c_messages, row.message_limit_per_cycle),
            cycle_cost=self._build_limit_detail(
                float(c_cost), float(row.cost_limit_per_cycle) if row.cost_limit_per_cycle else None
            ),
            absolute_tokens=self._build_limit_detail(row.total_tokens, row.token_limit_absolute),
            absolute_messages=self._build_limit_detail(
                row.total_messages, row.message_limit_absolute
            ),
            absolute_cost=self._build_limit_detail(
                float(row.total_cost),
                float(row.cost_limit_absolute) if row.cost_limit_absolute else None,
            ),
            cycle_start=cycle_start,
            cycle_end=cycle_end,
        )

    async def get_admin_list(
        self,
        page: int,
        page_size: int,
        search: str | None = None,
        blocked_only: bool = False,
    ) -> AdminUserUsageLimitListResponse:
        """Get paginated admin list with limits and usage.

        Args:
            page: Page number (1-based).
            page_size: Items per page.
            search: Optional search query.
            blocked_only: If True, only return manually blocked users.

        Returns:
            AdminUserUsageLimitListResponse with paginated results.
        """
        rows, total = await self.repo.get_all_with_stats(page, page_size, search, blocked_only)
        total_pages = self.repo.compute_total_pages(total, page_size)

        users = [self._build_admin_response_from_row(row) for row in rows]

        return AdminUserUsageLimitListResponse(
            users=users,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    async def update_limits(
        self,
        user_id: UUID,
        data: UsageLimitUpdate,
        admin_id: UUID,
    ) -> AdminUserUsageLimitResponse:
        """Update limits for a user (admin operation).

        Args:
            user_id: Target user UUID.
            data: New limit values.
            admin_id: Admin user UUID performing the update.

        Returns:
            Updated AdminUserUsageLimitResponse.

        Raises:
            ResourceNotFoundError: If target user does not exist.
        """
        limit = await self.repo.get_or_create_for_user(user_id)

        update_data = data.model_dump(exclude_unset=True)
        for field_name, value in update_data.items():
            setattr(limit, field_name, value)

        await self.db.flush()
        await self.db.refresh(limit)

        # Invalidate cache
        await self.invalidate_cache_static(user_id)

        logger.info(
            "usage_limits_updated",
            user_id=str(user_id),
            admin_id=str(admin_id),
            updated_fields=list(update_data.keys()),
        )

        return await self._build_admin_response(user_id)

    async def toggle_block(
        self,
        user_id: UUID,
        data: UsageBlockUpdate,
        admin_id: UUID,
    ) -> AdminUserUsageLimitResponse:
        """Toggle manual block for a user (admin operation).

        Args:
            user_id: Target user UUID.
            data: Block toggle data.
            admin_id: Admin user UUID performing the action.

        Returns:
            Updated AdminUserUsageLimitResponse.

        Raises:
            ResourceNotFoundError: If target user does not exist.
        """
        limit = await self.repo.get_or_create_for_user(user_id)

        limit.is_usage_blocked = data.is_usage_blocked
        limit.blocked_reason = data.blocked_reason if data.is_usage_blocked else None
        limit.blocked_at = datetime.now(UTC) if data.is_usage_blocked else None
        limit.blocked_by = admin_id if data.is_usage_blocked else None

        await self.db.flush()
        await self.db.refresh(limit)

        # Invalidate cache
        await self.invalidate_cache_static(user_id)

        logger.info(
            "usage_block_toggled",
            user_id=str(user_id),
            admin_id=str(admin_id),
            is_blocked=data.is_usage_blocked,
            reason=data.blocked_reason,
        )

        return await self._build_admin_response(user_id)

    async def create_default_limits(self, user_id: UUID) -> UserUsageLimit:
        """Create default limit record for a new user.

        Called from auth service during user registration.

        Args:
            user_id: Newly created user UUID.

        Returns:
            Created UserUsageLimit record.
        """
        limit = await self.repo.get_or_create_for_user(user_id)
        logger.info(
            "usage_limits_defaults_created",
            user_id=str(user_id),
        )
        return limit

    # ========================================================================
    # Private helpers
    # ========================================================================

    @staticmethod
    def _build_limit_detail(
        current: int | float,
        limit: int | float | None,
    ) -> LimitDetail:
        """Build a LimitDetail for a single dimension.

        Args:
            current: Current usage value.
            limit: Configured limit (None = unlimited).

        Returns:
            LimitDetail with computed percentage and exceeded flag.
        """
        if limit is None:
            return LimitDetail(
                current=current,
                limit=None,
                usage_pct=None,
                exceeded=False,
            )

        usage_pct = (current / limit * 100) if limit > 0 else 0.0
        return LimitDetail(
            current=current,
            limit=limit,
            usage_pct=round(usage_pct, 1),
            exceeded=current >= limit,
        )

    async def _build_admin_response(self, user_id: UUID) -> AdminUserUsageLimitResponse:
        """Build AdminUserUsageLimitResponse from fresh DB data.

        Fetches the row and delegates to _build_admin_response_from_row.

        Args:
            user_id: User UUID.

        Returns:
            AdminUserUsageLimitResponse with current data.

        Raises:
            ResourceNotFoundError: If user not found.
        """
        row = await self.repo.get_user_with_stats(user_id)
        if row is None:
            from src.core.exceptions import raise_user_not_found

            raise_user_not_found(user_id)

        return self._build_admin_response_from_row(row)

    def _build_admin_response_from_row(self, row: Row[Any]) -> AdminUserUsageLimitResponse:
        """Build AdminUserUsageLimitResponse from a repository row.

        Centralizes the row → response conversion (DRY). Used by both
        get_admin_list (from list query) and _build_admin_response (from single query).

        Args:
            row: SQLAlchemy Row from get_user_with_stats/get_all_with_stats.

        Returns:
            AdminUserUsageLimitResponse.
        """
        cycle_is_stale = self._is_cycle_stale(row.current_cycle_start, row.created_at)
        check = self._check_from_row(row, cycle_is_stale)
        c_tokens = 0 if cycle_is_stale else row.cycle_tokens
        c_messages = 0 if cycle_is_stale else row.cycle_messages
        c_cost = Decimal("0") if cycle_is_stale else row.cycle_cost

        return AdminUserUsageLimitResponse(
            user_id=row.user_id,
            email=row.email,
            full_name=row.full_name,
            is_active=row.is_active,
            is_usage_blocked=row.is_usage_blocked or False,
            blocked_reason=row.blocked_reason,
            blocked_at=row.blocked_at,
            blocked_by=row.blocked_by,
            token_limit_per_cycle=row.token_limit_per_cycle,
            message_limit_per_cycle=row.message_limit_per_cycle,
            cost_limit_per_cycle=row.cost_limit_per_cycle,
            token_limit_absolute=row.token_limit_absolute,
            message_limit_absolute=row.message_limit_absolute,
            cost_limit_absolute=row.cost_limit_absolute,
            cycle_tokens=c_tokens,
            cycle_messages=c_messages,
            cycle_cost=c_cost,
            total_tokens=row.total_tokens,
            total_messages=row.total_messages,
            total_cost=row.total_cost,
            status=check.status,
            created_at=row.created_at,
        )
