"""
Repository for Interests domain database operations.

Provides optimized queries for:
- Interest CRUD operations
- Weight calculations
- Notification tracking
- Deduplication checks
"""

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.config import settings
from src.core.constants import (
    INTEREST_ACTIVE_LIST_LIMIT,
    INTEREST_DECAY_FLOOR,
    INTEREST_INITIAL_NEGATIVE_SIGNALS,
    INTEREST_INITIAL_POSITIVE_SIGNALS,
    INTEREST_USER_LIST_LIMIT,
)
from src.domains.interests.models import (
    InterestNotification,
    InterestStatus,
    UserInterest,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class InterestRepository:
    """
    Repository for UserInterest database operations.

    Provides CRUD operations and specialized queries for:
    - Interest retrieval with computed weights
    - Deduplication via embedding similarity
    - Status transitions and updates
    """

    def __init__(self, db: AsyncSession):
        """Initialize repository with database session."""
        self.db = db

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    async def create(
        self,
        user_id: UUID,
        topic: str,
        category: str,
        embedding: list[float] | None = None,
    ) -> UserInterest:
        """
        Create a new interest for a user.

        Args:
            user_id: User UUID
            topic: Interest topic
            category: Interest category
            embedding: Optional embedding for deduplication

        Returns:
            Created UserInterest instance
        """
        interest = UserInterest(
            user_id=user_id,
            topic=topic,
            category=category,
            positive_signals=INTEREST_INITIAL_POSITIVE_SIGNALS,
            negative_signals=INTEREST_INITIAL_NEGATIVE_SIGNALS,
            status=InterestStatus.ACTIVE.value,
            last_mentioned_at=datetime.now(UTC),
            embedding=embedding,
        )
        self.db.add(interest)
        await self.db.flush()

        logger.info(
            "interest_created",
            user_id=str(user_id),
            interest_id=str(interest.id),
            topic=topic[:50],
            category=category,
        )

        return interest

    async def get_by_id(self, interest_id: UUID) -> UserInterest | None:
        """Get interest by ID."""
        result = await self.db.execute(select(UserInterest).where(UserInterest.id == interest_id))
        return result.scalar_one_or_none()

    async def get_by_user_and_topic(self, user_id: UUID, topic: str) -> UserInterest | None:
        """Get interest by user and exact topic match."""
        result = await self.db.execute(
            select(UserInterest).where(
                and_(
                    UserInterest.user_id == user_id,
                    UserInterest.topic == topic,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_user_and_topic_ci(self, user_id: UUID, topic: str) -> UserInterest | None:
        """Get interest by user and case-insensitive exact topic match.

        Closes the dedup hole where an embedding failure at creation time let
        pure case variants slip past ("Anthropic" vs "anthropic", ADR-131).

        Args:
            user_id: User UUID.
            topic: Topic to match, case-insensitively.

        Returns:
            The matching UserInterest, or None.
        """
        result = await self.db.execute(
            select(UserInterest).where(
                and_(
                    UserInterest.user_id == user_id,
                    func.lower(UserInterest.topic) == topic.lower(),
                )
            )
        )
        return result.scalars().first()

    async def get_by_user_topic_category(
        self, user_id: UUID, topic: str, category: str
    ) -> UserInterest | None:
        """
        Get interest by user, topic, and category.

        Used for uniqueness check when updating interests.
        Same topic can exist in different categories.

        Args:
            user_id: User UUID
            topic: Interest topic
            category: Interest category

        Returns:
            UserInterest if found, None otherwise
        """
        result = await self.db.execute(
            select(UserInterest).where(
                and_(
                    UserInterest.user_id == user_id,
                    UserInterest.topic == topic,
                    UserInterest.category == category,
                )
            )
        )
        return result.scalar_one_or_none()

    async def update(
        self,
        interest: UserInterest,
        topic: str | None = None,
        category: str | None = None,
        positive_signals: int | None = None,
        negative_signals: int | None = None,
        embedding: list[float] | None = None,
    ) -> UserInterest:
        """
        Update an existing interest.

        Only updates fields that are not None.
        Embedding should be regenerated by caller if topic changes.
        A topic change also resets the derived subject label to NULL so the
        clustering job relabels it (ADR-131), mirroring the extraction path.

        Args:
            interest: UserInterest to update
            topic: New topic (triggers embedding regeneration)
            category: New category
            positive_signals: New positive signals count
            negative_signals: New negative signals count
            embedding: New embedding (if topic changed)

        Returns:
            Updated UserInterest instance
        """
        if topic is not None and topic != interest.topic:
            interest.topic = topic
            interest.subject = None
        if category is not None:
            interest.category = category
        if positive_signals is not None:
            interest.positive_signals = positive_signals
        if negative_signals is not None:
            interest.negative_signals = negative_signals
        if embedding is not None:
            interest.embedding = embedding

        await self.db.flush()

        logger.info(
            "interest_updated",
            interest_id=str(interest.id),
            user_id=str(interest.user_id),
        )

        return interest

    async def get_all_for_user(
        self,
        user_id: UUID,
        status: str | None = None,
        limit: int = INTEREST_USER_LIST_LIMIT,
    ) -> list[UserInterest]:
        """
        Get all interests for a user.

        Args:
            user_id: User UUID
            status: Optional filter by status
            limit: Maximum results

        Returns:
            List of UserInterest, most recent first. Effective weights are
            computed in Python by callers (calculate_effective_weight);
            SQL cannot order by them.
        """
        query = select(UserInterest).where(UserInterest.user_id == user_id)

        if status:
            query = query.where(UserInterest.status == status)

        query = query.order_by(UserInterest.created_at.desc()).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_active_for_user(
        self,
        user_id: UUID,
        limit: int = INTEREST_ACTIVE_LIST_LIMIT,
    ) -> list[UserInterest]:
        """Get active interests for a user."""
        return await self.get_all_for_user(
            user_id=user_id,
            status=InterestStatus.ACTIVE.value,
            limit=limit,
        )

    async def get_for_dedup(
        self,
        user_id: UUID,
        limit: int,
    ) -> list[UserInterest]:
        """Get the interests deduplication must compare a new topic against.

        Every status, deliberately — NOT ``get_active_for_user``. A BLOCKED row
        that dedup cannot see is a subject the user rejected and the extractor
        re-creates under a neighbouring label (observed in production 25 minutes
        after the block, 2026-07-27); a DORMANT row that dedup cannot see is
        duplicated instead of being revived by ``consolidate_on_mention``.

        Args:
            user_id: Owner of the interests.
            limit: Scan window — ``settings.interest_dedup_scan_limit``, larger
                than the prompt window on purpose (rows are ordered newest
                first, so a short window drops the oldest, strongest ones).

        Returns:
            Interests of every status, most recent first.
        """
        return await self.get_all_for_user(user_id=user_id, status=None, limit=limit)

    async def delete(self, interest: UserInterest) -> None:
        """Delete an interest."""
        await self.db.delete(interest)

        logger.info(
            "interest_deleted",
            interest_id=str(interest.id),
            user_id=str(interest.user_id),
            topic=interest.topic[:50],
        )

    # =========================================================================
    # Weight Calculations
    # =========================================================================

    def calculate_weight(self, interest: UserInterest) -> float:
        """
        Calculate Bayesian confidence weight.

        Uses Beta distribution with configurable prior (default 2, 1) for optimistic start.
        Prior values are configurable via INTEREST_PRIOR_ALPHA and INTEREST_PRIOR_BETA
        environment variables.

        Args:
            interest: UserInterest instance

        Returns:
            Weight between 0.0 and 1.0
        """
        alpha = settings.interest_prior_alpha + interest.positive_signals
        beta = settings.interest_prior_beta + interest.negative_signals
        return alpha / (alpha + beta)

    def calculate_effective_weight(
        self,
        interest: UserInterest,
        decay_rate_per_day: float | None = None,
        now: datetime | None = None,
    ) -> float:
        """
        Calculate effective weight with temporal decay.

        The rate defaults to ``INTEREST_DECAY_RATE_PER_DAY``, never to a
        literal. It used to default to 0.01 while the setting was 0.005, and
        the one caller that omitted the argument — the notification RANKING —
        therefore applied a decay twice as fast as the one the API displayed:
        0.083 against 0.458 for an interest last mentioned 90 days ago. Every
        call site passes the setting today, so this fallback is unreachable in
        production; it exists so that omitting the argument can never again
        mean "some other rate".

        Args:
            interest: UserInterest instance
            decay_rate_per_day: Decay rate per day. None reads the setting.
            now: Current datetime (defaults to UTC now)

        Returns:
            Effective weight with decay applied
        """
        now = now or datetime.now(UTC)
        if decay_rate_per_day is None:
            decay_rate_per_day = settings.interest_decay_rate_per_day
        base_weight = self.calculate_weight(interest)

        # Calculate days since last mention
        days_since = (now - interest.last_mentioned_at).days
        decay = max(INTEREST_DECAY_FLOOR, 1.0 - (days_since * decay_rate_per_day))

        return base_weight * decay

    async def get_top_weighted_interests(
        self,
        user_id: UUID,
        top_percent: float = 0.2,
        min_count: int = 1,
        exclude_in_cooldown: bool = True,
        cooldown_hours: int = 24,
        now: datetime | None = None,
        decay_rate_per_day: float | None = None,
    ) -> list[tuple[UserInterest, float]]:
        """
        Get top N% weighted interests for notification selection.

        The decay rate defaults to the SETTING, not to
        ``calculate_effective_weight``'s signature default. This is the one
        path that decides which interest gets notified, and it was the only one
        of four taking the hardcoded 0.01 while the API, the extraction and the
        cleanup job all read ``INTEREST_DECAY_RATE_PER_DAY`` (0.005 in `.env`
        and `.env.example`). The reader was therefore shown a weight the ranking
        did not use — 0.458 displayed against 0.083 applied at 90 days without
        a mention — and ``top_percent`` cut a distribution nobody could see.

        Resolved in the BODY rather than as a default expression: a default is
        evaluated at import time and would freeze whatever the settings held
        then, which no test could change and no reload could refresh.

        Args:
            user_id: User UUID
            top_percent: Top percentage to select (default 20%)
            min_count: Minimum interests to return
            exclude_in_cooldown: Exclude recently notified
            cooldown_hours: Cooldown period in hours
            now: Current datetime
            decay_rate_per_day: Override the configured decay. Left to callers
                that own a different horizon (none today) — the default is the
                setting, so display and selection cannot drift again.

        Returns:
            List of (interest, effective_weight) tuples sorted by weight
        """
        now = now or datetime.now(UTC)
        if decay_rate_per_day is None:
            decay_rate_per_day = settings.interest_decay_rate_per_day

        # Get all active interests
        interests = await self.get_active_for_user(user_id)

        if not interests:
            return []

        # Calculate effective weights
        weighted = []
        cooldown_threshold = now - timedelta(hours=cooldown_hours)

        for interest in interests:
            # Skip if in cooldown
            if exclude_in_cooldown and interest.last_notified_at:
                if interest.last_notified_at > cooldown_threshold:
                    continue

            weight = self.calculate_effective_weight(
                interest, decay_rate_per_day=decay_rate_per_day, now=now
            )
            weighted.append((interest, weight))

        # Sort by weight descending
        weighted.sort(key=lambda x: x[1], reverse=True)

        # Select top N%
        count = max(min_count, int(len(weighted) * top_percent))
        return weighted[:count]

    # =========================================================================
    # Signal Updates
    # =========================================================================

    async def consolidate_on_mention(
        self,
        interest: UserInterest,
        now: datetime | None = None,
    ) -> None:
        """
        Consolidate interest on user mention.

        Increments positive_signals and updates last_mentioned_at.
        """
        now = now or datetime.now(UTC)
        interest.positive_signals += 1
        interest.last_mentioned_at = now

        # Reset dormant status if was dormant
        if interest.status == InterestStatus.DORMANT.value:
            interest.status = InterestStatus.ACTIVE.value
            interest.dormant_since = None

        logger.debug(
            "interest_consolidated",
            interest_id=str(interest.id),
            positive_signals=interest.positive_signals,
        )

    async def apply_feedback(
        self,
        interest: UserInterest,
        feedback: str,
    ) -> None:
        """
        Apply user feedback to interest.

        Args:
            interest: UserInterest instance
            feedback: "thumbs_up", "thumbs_down", or "block"
        """
        if feedback == "thumbs_up":
            interest.positive_signals += 2
        elif feedback == "thumbs_down":
            interest.negative_signals += 2
        elif feedback == "block":
            interest.status = InterestStatus.BLOCKED.value

        logger.info(
            "interest_feedback_applied",
            interest_id=str(interest.id),
            feedback=feedback,
            new_status=interest.status,
        )

    async def mark_notified(
        self,
        interest: UserInterest,
        now: datetime | None = None,
    ) -> None:
        """Mark interest as notified (update cooldown)."""
        now = now or datetime.now(UTC)
        interest.last_notified_at = now

    async def mark_dormant(
        self,
        interest: UserInterest,
        now: datetime | None = None,
    ) -> None:
        """Mark interest as dormant."""
        now = now or datetime.now(UTC)
        interest.status = InterestStatus.DORMANT.value
        interest.dormant_since = now

        logger.info(
            "interest_marked_dormant",
            interest_id=str(interest.id),
            user_id=str(interest.user_id),
        )

    async def reactivate(
        self,
        interest: UserInterest,
        now: datetime | None = None,
    ) -> UserInterest:
        """Reactivate a dormant interest by resetting it to a fresh state.

        Mirrors the initial state set by ``create()``: signal counters reset,
        status returns to ACTIVE, and ``last_mentioned_at`` is refreshed so the
        nightly cleanup will not immediately re-dormant it (a fresh interest's
        effective weight is ~0.75, above the 0.5 dormancy threshold). The topic,
        category, and embedding are preserved.

        Args:
            interest: UserInterest to reactivate.
            now: Current datetime (defaults to UTC now).

        Returns:
            The reactivated UserInterest.
        """
        now = now or datetime.now(UTC)
        interest.positive_signals = INTEREST_INITIAL_POSITIVE_SIGNALS
        interest.negative_signals = INTEREST_INITIAL_NEGATIVE_SIGNALS
        interest.status = InterestStatus.ACTIVE.value
        interest.last_mentioned_at = now
        interest.last_notified_at = None
        interest.dormant_since = None

        await self.db.flush()

        logger.info(
            "interest_reactivated",
            interest_id=str(interest.id),
            user_id=str(interest.user_id),
        )
        return interest

    # =========================================================================
    # Bulk Operations
    # =========================================================================

    async def merge_interests(self, keep: UserInterest, dup: UserInterest) -> UserInterest:
        """Merge a duplicate interest into a kept one (ADR-131 retro-merge).

        Signals are summed, activity timestamps take the max, notifications
        are repointed to preserve the audit trail and rarity counts, and the
        kept interest's subject resets to NULL so the clustering job relabels it.
        BLOCKED status on either side wins (user intent is preserved).

        Args:
            keep: The interest that survives.
            dup: The interest merged away (deleted).

        Returns:
            The kept, updated UserInterest.
        """
        keep.positive_signals += dup.positive_signals
        keep.negative_signals += dup.negative_signals
        keep.last_mentioned_at = max(keep.last_mentioned_at, dup.last_mentioned_at)
        if dup.last_notified_at and (
            keep.last_notified_at is None or dup.last_notified_at > keep.last_notified_at
        ):
            keep.last_notified_at = dup.last_notified_at
        if dup.status == InterestStatus.BLOCKED.value:
            keep.status = InterestStatus.BLOCKED.value
        keep.subject = None

        await self.db.execute(
            update(InterestNotification)
            .where(InterestNotification.interest_id == dup.id)
            .values(interest_id=keep.id)
        )
        await self.db.delete(dup)
        await self.db.flush()

        logger.info(
            "interests_merged",
            kept_id=str(keep.id),
            duplicate_id=str(dup.id),
            kept_topic=keep.topic[:50],
            positive_signals=keep.positive_signals,
        )
        return keep

    async def delete_all_for_user(self, user_id: UUID) -> int:
        """
        Delete all interests for a user (GDPR erasure).

        Args:
            user_id: User UUID

        Returns:
            Number of deleted interests
        """
        result = await self.db.execute(delete(UserInterest).where(UserInterest.user_id == user_id))

        deleted: int = result.rowcount  # type: ignore[attr-defined]
        if deleted > 0:
            logger.info(
                "interests_delete_all_for_user",
                user_id=str(user_id),
                count=deleted,
            )

        return deleted

    async def delete_dormant_older_than(
        self,
        days: int,
        now: datetime | None = None,
    ) -> int:
        """
        Delete interests dormant for more than N days.

        Args:
            days: Days threshold for deletion
            now: Current datetime

        Returns:
            Number of deleted interests
        """
        now = now or datetime.now(UTC)
        threshold = now - timedelta(days=days)

        result = await self.db.execute(
            delete(UserInterest).where(
                and_(
                    UserInterest.status == InterestStatus.DORMANT.value,
                    UserInterest.dormant_since <= threshold,
                )
            )
        )

        deleted: int = result.rowcount  # type: ignore[attr-defined]
        if deleted > 0:
            logger.info(
                "dormant_interests_deleted",
                count=deleted,
                threshold_days=days,
            )

        return deleted

    async def get_interests_for_embedding_update(
        self,
        limit: int = INTEREST_USER_LIST_LIMIT,
    ) -> list[UserInterest]:
        """Get interests without embeddings for batch embedding update."""
        result = await self.db.execute(
            select(UserInterest).where(UserInterest.embedding.is_(None)).limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_user_ids(self, user_ids: list[UUID]) -> dict[UUID, int]:
        """
        Count interests per user for multiple users (batch operation).

        Args:
            user_ids: List of user UUIDs

        Returns:
            Dict mapping user_id to interest count
        """
        if not user_ids:
            return {}

        from sqlalchemy import func

        result = await self.db.execute(
            select(UserInterest.user_id, func.count(UserInterest.id))
            .where(UserInterest.user_id.in_(user_ids))
            .group_by(UserInterest.user_id)
        )

        counts = {row[0]: row[1] for row in result.all()}

        # Fill in zeros for users with no interests
        for user_id in user_ids:
            if user_id not in counts:
                counts[user_id] = 0

        return counts


class InterestNotificationRepository:
    """
    Repository for InterestNotification database operations.

    Provides queries for:
    - Notification tracking
    - Quota checking
    - Deduplication
    """

    def __init__(self, db: AsyncSession):
        """Initialize repository with database session."""
        self.db = db

    async def count_history_for_user(self, user_id: UUID) -> int:
        """Exact number of notifications this account's history holds.

        The ONE implementation of "how many are there": ``get_history``
        delegates its own total here rather than repeating the filter, so the
        hub badge and the page it describes cannot drift apart (ADR-185). It
        also lets the badge be answered without paying for a page of rows.

        Args:
            user_id: Owner.

        Returns:
            Exact count.
        """
        result = await self.db.execute(
            select(func.count())
            .select_from(InterestNotification)
            .where(InterestNotification.user_id == user_id)
        )
        return int(result.scalar() or 0)

    async def get_history(
        self,
        user_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[InterestNotification], int]:
        """One page of this user's interest notifications, newest first.

        Mirrors ``HeartbeatNotificationRepository.get_history`` deliberately:
        the two histories share a panel and a card, so a divergence in ordering
        or in what "total" means would be visible side by side.

        The total is an EXACT aggregate over the whole set, never the length of
        the page (ADR-185): a figure shown to the reader is a claim, and
        "10 of 10" on an account with 200 notifications is a false one.

        Args:
            user_id: Owner — scopes both reads.
            limit: Page size.
            offset: Page offset.

        Returns:
            Tuple of (notifications, exact total).
        """
        # The total comes from `count_history_for_user`, never from a second
        # copy of the filter: the hub badge and this page describe one set, and
        # two filters for one figure is how they start disagreeing (ADR-185).
        total = await self.count_history_for_user(user_id)

        result = await self.db.execute(
            select(InterestNotification)
            # Eager, not lazy: the caller reads `notification.interest.topic`,
            # and under asyncio touching a lazy relationship after the query
            # returned raises `MissingGreenlet` — a 500 on a page that looks
            # perfectly fine in a mocked test.
            .options(selectinload(InterestNotification.interest))
            .where(InterestNotification.user_id == user_id)
            .order_by(InterestNotification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), total

    async def create(
        self,
        user_id: UUID,
        interest_id: UUID | None,
        run_id: str,
        content_hash: str,
        source: str,
        content_embedding: list[float] | None = None,
        content: str | None = None,
    ) -> InterestNotification:
        """
        Create a notification record.

        Args:
            user_id: User UUID
            interest_id: Interest UUID (nullable)
            run_id: Unique run ID for token tracking
            content_hash: SHA256 hash of content
            source: Content source
            content_embedding: Optional embedding
            content: The message the user received. Optional and last so every
                existing caller keeps working; a row without it renders without
                its paragraph rather than with an invented one.

        Returns:
            Created InterestNotification instance
        """
        notification = InterestNotification(
            user_id=user_id,
            interest_id=interest_id,
            run_id=run_id,
            content=content,
            content_hash=content_hash,
            source=source,
            content_embedding=content_embedding,
        )
        self.db.add(notification)
        await self.db.flush()

        logger.info(
            "interest_notification_created",
            user_id=str(user_id),
            notification_id=str(notification.id),
            source=source,
            run_id=run_id,
        )

        return notification

    async def get_by_id(self, notification_id: UUID) -> InterestNotification | None:
        """Get notification by ID."""
        result = await self.db.execute(
            select(InterestNotification).where(InterestNotification.id == notification_id)
        )
        return result.scalar_one_or_none()

    async def count_today_for_user(
        self,
        user_id: UUID,
        user_timezone: str = "UTC",
        now: datetime | None = None,
    ) -> int:
        """
        Count notifications sent today for a user.

        Args:
            user_id: User UUID
            user_timezone: User's timezone
            now: Current datetime

        Returns:
            Count of notifications today
        """
        now = now or datetime.now(UTC)

        # Calculate start of today in user's timezone
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
                    InterestNotification.user_id == user_id,
                    InterestNotification.created_at >= today_start,
                )
            )
        )
        return result.scalar() or 0

    async def get_last_for_user(
        self,
        user_id: UUID,
    ) -> InterestNotification | None:
        """Get the most recent notification for a user."""
        result = await self.db.execute(
            select(InterestNotification)
            .where(InterestNotification.user_id == user_id)
            .order_by(InterestNotification.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_recent_for_user(
        self,
        user_id: UUID,
        days: int,
        now: datetime | None = None,
    ) -> list[InterestNotification]:
        """Get a user's notifications within a lookback window.

        Feeds subject cooldown and rarity counts for selection (ADR-131).
        Uses ix_interest_notifications_user_created.

        Args:
            user_id: User UUID.
            days: Lookback window in days.
            now: Current datetime (defaults to UTC now).

        Returns:
            Notifications ordered most recent first.
        """
        now = now or datetime.now(UTC)
        threshold = now - timedelta(days=days)
        result = await self.db.execute(
            select(InterestNotification)
            .where(
                and_(
                    InterestNotification.user_id == user_id,
                    InterestNotification.created_at >= threshold,
                )
            )
            .order_by(InterestNotification.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_recent_for_interest(
        self,
        interest_id: UUID,
        days: int | None = None,
        now: datetime | None = None,
    ) -> list[InterestNotification]:
        """
        Get recent notifications for an interest.

        Used for content deduplication.
        """
        if days is None:
            days = settings.interest_content_lookback_days
        now = now or datetime.now(UTC)
        threshold = now - timedelta(days=days)

        result = await self.db.execute(
            select(InterestNotification)
            .where(
                and_(
                    InterestNotification.interest_id == interest_id,
                    InterestNotification.created_at >= threshold,
                )
            )
            .order_by(InterestNotification.created_at.desc())
        )
        return list(result.scalars().all())

    async def check_content_hash_exists(
        self,
        user_id: UUID,
        content_hash: str,
        days: int | None = None,
        now: datetime | None = None,
    ) -> bool:
        """
        Check if content hash already exists (exact deduplication).

        Args:
            user_id: User UUID
            content_hash: SHA256 hash to check
            days: Lookback period
            now: Current datetime

        Returns:
            True if duplicate exists
        """
        if days is None:
            days = settings.interest_content_lookback_days
        now = now or datetime.now(UTC)
        threshold = now - timedelta(days=days)

        result = await self.db.execute(
            select(func.count()).where(
                and_(
                    InterestNotification.user_id == user_id,
                    InterestNotification.content_hash == content_hash,
                    InterestNotification.created_at >= threshold,
                )
            )
        )
        return (result.scalar() or 0) > 0

    async def update_feedback_by_run_id(
        self,
        run_id: str,
        user_id: UUID,
        feedback: str,
    ) -> bool:
        """Record the user's verdict on the notification identified by ``run_id``.

        Replaces an unused ``update_feedback(notification_id, feedback)`` that
        had no caller and no ownership filter: the audit column stayed NULL on
        every one of the 989 production rows, so anyone reading that table —
        including a dashboard — concluded the user never gave feedback, while
        the interest itself was correctly updated by ``apply_feedback``.

        ``run_id`` is the join the archived chat card already carries in its
        metadata (verified in production: 166/166 archived cards have one), so
        the verdict lands on the exact notification the user was looking at
        rather than on a guessed "most recent" row.

        Args:
            run_id: Unique run identifier of the notification.
            user_id: Owner — scopes the write, so a forged run_id from another
                tenant updates nothing.
            feedback: One of ``thumbs_up``, ``thumbs_down``, ``block``.

        Returns:
            True when a row was updated.
        """
        result = await self.db.execute(
            update(InterestNotification)
            .where(
                and_(
                    InterestNotification.run_id == run_id,
                    InterestNotification.user_id == user_id,
                )
            )
            .values(user_feedback=feedback)
        )
        return result.rowcount > 0  # type: ignore[attr-defined, no-any-return]
