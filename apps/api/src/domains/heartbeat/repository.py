"""
Heartbeat Autonome domain repository.

Provides database operations for HeartbeatNotification audit records:
- CRUD operations
- Quota checking (count_today_for_user)
- History queries with pagination
- Feedback updates
- Content hash deduplication
"""

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.heartbeat.models import HeartbeatNotification

logger = structlog.get_logger(__name__)


class HeartbeatNotificationRepository:
    """Repository for HeartbeatNotification database operations.

    Provides queries for:
    - Notification creation and retrieval
    - Quota checking (daily count per user)
    - Paginated history
    - Content hash deduplication
    - User feedback
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize repository with database session."""
        self.db = db

    async def create(
        self,
        user_id: UUID,
        run_id: str,
        content: str,
        content_hash: str,
        sources_used: str,
        decision_reason: str | None = None,
        priority: str = "low",
        tokens_in: int = 0,
        tokens_out: int = 0,
        model_name: str | None = None,
    ) -> HeartbeatNotification:
        """Create an audit record for a sent heartbeat notification.

        Args:
            user_id: User UUID.
            run_id: Unique run ID for token tracking.
            content: The notification message sent.
            content_hash: SHA256 hash for deduplication.
            sources_used: JSON string of source types.
            decision_reason: LLM's reason for deciding to notify.
            priority: Notification priority (low, medium, high).
            tokens_in: Total input tokens consumed.
            tokens_out: Total output tokens consumed.
            model_name: LLM model used.

        Returns:
            Created HeartbeatNotification instance.
        """
        notification = HeartbeatNotification(
            user_id=user_id,
            run_id=run_id,
            content=content,
            content_hash=content_hash,
            sources_used=sources_used,
            decision_reason=decision_reason,
            priority=priority,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model_name=model_name,
        )
        self.db.add(notification)
        await self.db.flush()

        logger.info(
            "heartbeat_notification_created",
            user_id=str(user_id),
            notification_id=str(notification.id),
            priority=priority,
            run_id=run_id,
        )

        return notification

    async def get_by_id(
        self,
        notification_id: UUID,
    ) -> HeartbeatNotification | None:
        """Get notification by ID."""
        result = await self.db.execute(
            select(HeartbeatNotification).where(HeartbeatNotification.id == notification_id)
        )
        return result.scalar_one_or_none()

    async def count_today_for_user(
        self,
        user_id: UUID,
        user_timezone: str = "UTC",
        now: datetime | None = None,
    ) -> int:
        """Count notifications sent today for a user.

        Args:
            user_id: User UUID.
            user_timezone: User's IANA timezone name.
            now: Current datetime (for testing).

        Returns:
            Count of notifications sent today.
        """
        now = now or datetime.now(UTC)

        try:
            user_tz: ZoneInfo | timezone = ZoneInfo(user_timezone)
        except (KeyError, ValueError):
            user_tz = UTC

        user_now = now.astimezone(user_tz)
        today_start = datetime(
            user_now.year, user_now.month, user_now.day, tzinfo=user_tz
        ).astimezone(UTC)

        result = await self.db.execute(
            select(func.count()).where(
                and_(
                    HeartbeatNotification.user_id == user_id,
                    HeartbeatNotification.created_at >= today_start,
                )
            )
        )
        return result.scalar() or 0

    async def get_last_for_user(
        self,
        user_id: UUID,
    ) -> HeartbeatNotification | None:
        """Get the most recent notification for a user."""
        result = await self.db.execute(
            select(HeartbeatNotification)
            .where(HeartbeatNotification.user_id == user_id)
            .order_by(HeartbeatNotification.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_recent_by_user(
        self,
        user_id: UUID,
        limit: int = 5,
    ) -> list[HeartbeatNotification]:
        """Get recent notifications for a user (for anti-redundancy).

        Args:
            user_id: User UUID.
            limit: Maximum number of notifications to return.

        Returns:
            List of recent HeartbeatNotification (newest first).
        """
        result = await self.db.execute(
            select(HeartbeatNotification)
            .where(HeartbeatNotification.user_id == user_id)
            .order_by(HeartbeatNotification.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_history(
        self,
        user_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[HeartbeatNotification], int]:
        """Get paginated notification history for a user.

        Args:
            user_id: User UUID.
            limit: Page size.
            offset: Page offset.

        Returns:
            Tuple of (notifications, total_count).
        """
        base_filter = HeartbeatNotification.user_id == user_id

        # Total count
        count_result = await self.db.execute(select(func.count()).where(base_filter))
        total = count_result.scalar() or 0

        # Paginated results
        result = await self.db.execute(
            select(HeartbeatNotification)
            .where(base_filter)
            .order_by(HeartbeatNotification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        notifications = list(result.scalars().all())

        return notifications, total

    async def check_content_hash_exists(
        self,
        user_id: UUID,
        content_hash: str,
        days: int = 7,
        now: datetime | None = None,
    ) -> bool:
        """Check if content hash already exists (exact deduplication).

        Args:
            user_id: User UUID.
            content_hash: SHA256 hash to check.
            days: Lookback period in days.
            now: Current datetime (for testing).

        Returns:
            True if duplicate exists within the lookback period.
        """
        now = now or datetime.now(UTC)
        threshold = now - timedelta(days=days)

        result = await self.db.execute(
            select(func.count()).where(
                and_(
                    HeartbeatNotification.user_id == user_id,
                    HeartbeatNotification.content_hash == content_hash,
                    HeartbeatNotification.created_at >= threshold,
                )
            )
        )
        return (result.scalar() or 0) > 0

    async def update_feedback(
        self,
        notification_id: UUID,
        user_id: UUID,
        feedback: str,
    ) -> bool:
        """Update user feedback on a notification.

        Args:
            notification_id: Notification UUID.
            user_id: User UUID (for ownership check).
            feedback: Feedback value (thumbs_up or thumbs_down).

        Returns:
            True if updated, False if not found or not owned.
        """
        result = await self.db.execute(
            update(HeartbeatNotification)
            .where(
                and_(
                    HeartbeatNotification.id == notification_id,
                    HeartbeatNotification.user_id == user_id,
                )
            )
            .values(user_feedback=feedback)
        )
        return result.rowcount > 0  # type: ignore[attr-defined, no-any-return]
