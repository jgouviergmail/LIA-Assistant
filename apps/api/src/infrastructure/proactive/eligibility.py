"""
Eligibility Checking for Proactive Tasks.

Provides generic eligibility checks that apply to all proactive tasks:
- Feature enabled check
- Time window check (user timezone)
- Daily quota check
- Global cooldown check
- Activity cooldown check (don't interrupt active users)

Task-specific eligibility is handled by the ProactiveTask.check_eligibility() method.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class EligibilityReason(str, Enum):
    """Reasons for eligibility check results."""

    ELIGIBLE = "eligible"
    FEATURE_DISABLED = "feature_disabled"
    OUTSIDE_TIME_WINDOW = "outside_time_window"
    QUOTA_EXCEEDED = "quota_exceeded"
    GLOBAL_COOLDOWN = "global_cooldown"
    CROSS_TYPE_COOLDOWN = "cross_type_cooldown"
    ACTIVITY_COOLDOWN = "activity_cooldown"
    TASK_SPECIFIC = "task_specific"
    NO_TARGET = "no_target"


@dataclass
class EligibilityResult:
    """
    Result of eligibility check.

    Attributes:
        eligible: Whether user is eligible
        reason: Reason for the result
        details: Additional details (e.g., time until eligible)
    """

    eligible: bool
    reason: EligibilityReason
    details: dict[str, Any] | None = None

    @classmethod
    def success(cls) -> "EligibilityResult":
        """Create a successful eligibility result."""
        return cls(eligible=True, reason=EligibilityReason.ELIGIBLE)

    @classmethod
    def failure(
        cls,
        reason: EligibilityReason,
        details: dict[str, Any] | None = None,
    ) -> "EligibilityResult":
        """Create a failed eligibility result."""
        return cls(eligible=False, reason=reason, details=details)


class EligibilityChecker:
    """
    Generic eligibility checker for proactive tasks.

    Performs common eligibility checks that apply to all proactive tasks.
    Task-specific checks are delegated to ProactiveTask.check_eligibility().

    Checks performed (in order):
    1. Feature enabled (task-specific setting)
    2. Time window (user timezone)
    3. Daily quota (notifications sent today)
    4. Global cooldown (time since last notification)
    5. Activity cooldown (time since last user message)

    Usage:
        >>> checker = EligibilityChecker(
        ...     task_type="interest",
        ...     enabled_field="interests_enabled",
        ...     start_hour_field="interests_notify_start_hour",
        ...     end_hour_field="interests_notify_end_hour",
        ...     min_per_day_field="interests_notify_min_per_day",
        ...     max_per_day_field="interests_notify_max_per_day",
        ... )
        >>> result = await checker.check(user, db, now)
    """

    def __init__(
        self,
        task_type: str,
        enabled_field: str,
        start_hour_field: str,
        end_hour_field: str,
        min_per_day_field: str,
        max_per_day_field: str,
        notification_model: Any = None,  # SQLAlchemy model class with user_id, created_at
        global_cooldown_hours: int = 2,
        activity_cooldown_minutes: int = 5,
        interval_minutes: int = 15,
        cross_type_models: list[Any] | None = None,
        cross_type_cooldown_minutes: int = 30,
        default_start_hour: int = 9,
        default_end_hour: int = 22,
        default_min_per_day: int = 1,
        default_max_per_day: int = 3,
    ):
        """
        Initialize eligibility checker.

        Args:
            task_type: Task type identifier (for logging)
            enabled_field: User model field for feature toggle
            start_hour_field: User model field for notification start hour
            end_hour_field: User model field for notification end hour
            min_per_day_field: User model field for min notifications per day
            max_per_day_field: User model field for max notifications per day
            notification_model: SQLAlchemy model for notifications (for quota check)
            global_cooldown_hours: Minimum hours between any notifications
            activity_cooldown_minutes: Don't notify if user active within N minutes
            interval_minutes: Scheduler interval in minutes (used by runner for
                adaptive frequency calculation)
            cross_type_models: Additional notification models from other task types
                to check for cross-type cooldown. Prevents notification bursts
                from different proactive task types.
            cross_type_cooldown_minutes: Minimum minutes between notifications of
                different proactive types.
            default_start_hour: Fallback start hour if user field is missing.
            default_end_hour: Fallback end hour if user field is missing.
            default_min_per_day: Fallback min per day if user field is missing.
            default_max_per_day: Fallback max per day if user field is missing.
        """
        self.task_type = task_type
        self.enabled_field = enabled_field
        self.start_hour_field = start_hour_field
        self.end_hour_field = end_hour_field
        self.min_per_day_field = min_per_day_field
        self.max_per_day_field = max_per_day_field
        self.notification_model = notification_model
        self.global_cooldown_hours = global_cooldown_hours
        self.activity_cooldown_minutes = activity_cooldown_minutes
        self.interval_minutes = interval_minutes
        self.cross_type_models = cross_type_models or []
        self.cross_type_cooldown_minutes = cross_type_cooldown_minutes
        self.default_start_hour = default_start_hour
        self.default_end_hour = default_end_hour
        self.default_min_per_day = default_min_per_day
        self.default_max_per_day = default_max_per_day

    async def check(
        self,
        user: Any,
        db: AsyncSession,
        now: datetime | None = None,
    ) -> EligibilityResult:
        """
        Perform all eligibility checks.

        Args:
            user: User model instance
            db: Database session
            now: Current datetime (defaults to UTC now)

        Returns:
            EligibilityResult with eligibility status and reason
        """
        now = now or datetime.now(UTC)

        # 1. Feature enabled check
        result = self._check_feature_enabled(user)
        if not result.eligible:
            return result

        # 2. Time window check
        result = self._check_time_window(user, now)
        if not result.eligible:
            return result

        # 3. Daily quota check
        if self.notification_model:
            result = await self._check_daily_quota(user, db, now)
            if not result.eligible:
                return result

        # 4. Global cooldown check (same task type)
        if self.notification_model:
            result = await self._check_global_cooldown(user, db, now)
            if not result.eligible:
                return result

        # 5. Cross-type cooldown check (other proactive task types)
        if self.cross_type_models:
            result = await self._check_cross_type_cooldown(user, db, now)
            if not result.eligible:
                return result

        # 6. Activity cooldown check
        result = await self._check_activity_cooldown(user, db, now)
        if not result.eligible:
            return result

        logger.debug(
            "eligibility_check_passed",
            task_type=self.task_type,
            user_id=str(user.id),
        )
        return EligibilityResult.success()

    def _check_feature_enabled(self, user: Any) -> EligibilityResult:
        """Check if feature is enabled for user."""
        enabled = getattr(user, self.enabled_field, False)
        if not enabled:
            logger.debug(
                "eligibility_feature_disabled",
                task_type=self.task_type,
                user_id=str(user.id),
                field=self.enabled_field,
            )
            return EligibilityResult.failure(
                EligibilityReason.FEATURE_DISABLED,
                {"field": self.enabled_field},
            )
        return EligibilityResult.success()

    def _check_time_window(self, user: Any, now: datetime) -> EligibilityResult:
        """Check if current time is within user's notification window."""
        # Get user timezone
        user_tz_str = getattr(user, "timezone", None) or "UTC"
        try:
            user_tz: ZoneInfo | timezone = ZoneInfo(user_tz_str)
        except (KeyError, ValueError):
            user_tz = UTC

        # Convert now to user's timezone
        user_now = now.astimezone(user_tz)
        current_hour = user_now.hour

        # Get time window settings
        start_hour = getattr(user, self.start_hour_field, self.default_start_hour)
        end_hour = getattr(user, self.end_hour_field, self.default_end_hour)

        # Check if current hour is within window
        if start_hour <= end_hour:
            # Normal case: e.g., 9-22
            in_window = start_hour <= current_hour < end_hour
        else:
            # Overnight case: e.g., 22-9 (crosses midnight)
            in_window = current_hour >= start_hour or current_hour < end_hour

        if not in_window:
            logger.debug(
                "eligibility_outside_time_window",
                task_type=self.task_type,
                user_id=str(user.id),
                current_hour=current_hour,
                start_hour=start_hour,
                end_hour=end_hour,
                user_tz=user_tz_str,
            )
            return EligibilityResult.failure(
                EligibilityReason.OUTSIDE_TIME_WINDOW,
                {
                    "current_hour": current_hour,
                    "start_hour": start_hour,
                    "end_hour": end_hour,
                    "user_timezone": user_tz_str,
                },
            )
        return EligibilityResult.success()

    async def _check_daily_quota(
        self,
        user: Any,
        db: AsyncSession,
        now: datetime,
    ) -> EligibilityResult:
        """Check if user has exceeded daily notification quota."""
        if not self.notification_model:
            return EligibilityResult.success()

        # Get user timezone for "today" calculation
        user_tz_str = getattr(user, "timezone", None) or "UTC"
        try:
            user_tz: ZoneInfo | timezone = ZoneInfo(user_tz_str)
        except (KeyError, ValueError):
            user_tz = UTC

        # Calculate start of today in user's timezone
        user_now = now.astimezone(user_tz)
        today_start = datetime(
            user_now.year, user_now.month, user_now.day, tzinfo=user_tz
        ).astimezone(UTC)

        # Count notifications sent today
        model = self.notification_model
        query = select(func.count()).where(
            model.user_id == user.id,
            model.created_at >= today_start,
        )
        result = await db.execute(query)
        today_count = result.scalar() or 0

        # Get max per day setting
        max_per_day = getattr(user, self.max_per_day_field, self.default_max_per_day)

        if today_count >= max_per_day:
            logger.debug(
                "eligibility_quota_exceeded",
                task_type=self.task_type,
                user_id=str(user.id),
                today_count=today_count,
                max_per_day=max_per_day,
            )
            return EligibilityResult.failure(
                EligibilityReason.QUOTA_EXCEEDED,
                {"today_count": today_count, "max_per_day": max_per_day},
            )
        return EligibilityResult.success()

    async def _check_global_cooldown(
        self,
        user: Any,
        db: AsyncSession,
        now: datetime,
    ) -> EligibilityResult:
        """Check if enough time has passed since last notification."""
        if not self.notification_model:
            return EligibilityResult.success()

        # Get last notification time
        model = self.notification_model
        query = (
            select(model.created_at)
            .where(model.user_id == user.id)
            .order_by(model.created_at.desc())
            .limit(1)
        )
        result = await db.execute(query)
        last_notification = result.scalar()

        if last_notification:
            cooldown_threshold = now - timedelta(hours=self.global_cooldown_hours)
            if last_notification > cooldown_threshold:
                time_since = now - last_notification
                time_until_eligible = timedelta(hours=self.global_cooldown_hours) - time_since
                logger.debug(
                    "eligibility_global_cooldown",
                    task_type=self.task_type,
                    user_id=str(user.id),
                    last_notification=last_notification.isoformat(),
                    cooldown_hours=self.global_cooldown_hours,
                    minutes_until_eligible=time_until_eligible.total_seconds() / 60,
                )
                return EligibilityResult.failure(
                    EligibilityReason.GLOBAL_COOLDOWN,
                    {
                        "last_notification": last_notification.isoformat(),
                        "cooldown_hours": self.global_cooldown_hours,
                        "minutes_until_eligible": time_until_eligible.total_seconds() / 60,
                    },
                )
        return EligibilityResult.success()

    async def _check_cross_type_cooldown(
        self,
        user: Any,
        db: AsyncSession,
        now: datetime,
    ) -> EligibilityResult:
        """Check if a notification from another proactive type was sent recently.

        Prevents notification bursts where, e.g., an interest notification and
        a heartbeat notification fire within minutes of each other for the same user.

        Only checks cross_type_models (other task types), NOT self.notification_model
        (which is handled by _check_global_cooldown).
        """
        if not self.cross_type_models:
            return EligibilityResult.success()

        cooldown_threshold = now - timedelta(minutes=self.cross_type_cooldown_minutes)

        for model in self.cross_type_models:
            query = (
                select(model.created_at)
                .where(model.user_id == user.id)
                .where(model.created_at > cooldown_threshold)
                .order_by(model.created_at.desc())
                .limit(1)
            )
            result = await db.execute(query)
            last_cross_notification = result.scalar()

            if last_cross_notification:
                time_since = now - last_cross_notification
                time_until = timedelta(minutes=self.cross_type_cooldown_minutes) - time_since
                logger.debug(
                    "eligibility_cross_type_cooldown",
                    task_type=self.task_type,
                    user_id=str(user.id),
                    cross_model=model.__tablename__,
                    last_notification=last_cross_notification.isoformat(),
                    cooldown_minutes=self.cross_type_cooldown_minutes,
                    minutes_until_eligible=time_until.total_seconds() / 60,
                )
                return EligibilityResult.failure(
                    EligibilityReason.CROSS_TYPE_COOLDOWN,
                    {
                        "cross_model": model.__tablename__,
                        "last_notification": last_cross_notification.isoformat(),
                        "cooldown_minutes": self.cross_type_cooldown_minutes,
                        "minutes_until_eligible": time_until.total_seconds() / 60,
                    },
                )

        return EligibilityResult.success()

    async def _check_activity_cooldown(
        self,
        user: Any,
        db: AsyncSession,
        now: datetime,
    ) -> EligibilityResult:
        """Check if user is currently active (don't interrupt)."""
        # Try to get last activity from user model
        last_activity = getattr(user, "last_chat_activity_at", None)

        # If not available on user, try to query messages table
        if last_activity is None:
            try:
                # Message model may not exist yet - graceful fallback
                from src.domains.chat.models import Message  # type: ignore[attr-defined]

                query = (
                    select(Message.created_at)
                    .where(Message.user_id == user.id)
                    .order_by(Message.created_at.desc())
                    .limit(1)
                )
                result = await db.execute(query)
                last_activity = result.scalar()
            except Exception:
                # If message table doesn't exist or query fails, skip this check
                return EligibilityResult.success()

        if last_activity:
            activity_threshold = now - timedelta(minutes=self.activity_cooldown_minutes)
            if last_activity > activity_threshold:
                time_since = now - last_activity
                logger.debug(
                    "eligibility_activity_cooldown",
                    task_type=self.task_type,
                    user_id=str(user.id),
                    last_activity=last_activity.isoformat(),
                    cooldown_minutes=self.activity_cooldown_minutes,
                    seconds_since_activity=time_since.total_seconds(),
                )
                return EligibilityResult.failure(
                    EligibilityReason.ACTIVITY_COOLDOWN,
                    {
                        "last_activity": last_activity.isoformat(),
                        "cooldown_minutes": self.activity_cooldown_minutes,
                        "seconds_since_activity": time_since.total_seconds(),
                    },
                )
        return EligibilityResult.success()

    def should_send_notification(
        self,
        user: Any,
        today_count: int,
        window_hours: int,
        elapsed_hours: float,
        interval_minutes: int = 15,
    ) -> tuple[bool, dict[str, Any]]:
        """
        Time-aware probabilistic check with guaranteed minimum delivery.

        Algorithm:
        1. If already sent max → False
        2. GUARANTEE ZONE: In last 20% of window, if below min → True (force send)
        3. ADAPTIVE PROBABILITY: Uses remaining time to calculate probability that
           increases as the window progresses, ensuring targets are met.
        4. DEFICIT BOOST: If behind schedule vs time-based expectation, boost up to 2x.

        Previous bugs fixed:
        - Old boost formula (target * today_count/max) was structurally unable to boost
        - No guarantee zone meant min_per_day was never enforced
        - Flat probability across the entire window caused unreliable delivery

        Args:
            user: User model instance
            today_count: Notifications already sent today
            window_hours: Total hours in notification window
            elapsed_hours: Hours elapsed since window start
            interval_minutes: Scheduler interval in minutes

        Returns:
            Tuple of (should_send, debug_info) for logging
        """
        import random

        min_per_day = getattr(user, self.min_per_day_field, self.default_min_per_day)
        max_per_day = getattr(user, self.max_per_day_field, self.default_max_per_day)

        debug_info: dict[str, Any] = {
            "min_per_day": min_per_day,
            "max_per_day": max_per_day,
            "today_count": today_count,
            "window_hours": window_hours,
            "elapsed_hours": round(elapsed_hours, 2),
        }

        # If already sent max, don't send more
        if today_count >= max_per_day:
            debug_info["decision"] = "quota_reached"
            return False, debug_info

        # Safety: avoid division by zero
        if window_hours <= 0:
            debug_info["decision"] = "invalid_window"
            return False, debug_info

        # Time fraction through the window (0.0 = start, 1.0 = end)
        time_fraction = min(max(elapsed_hours / window_hours, 0.0), 1.0)
        remaining_fraction = max(0.0, 1.0 - time_fraction)

        target_per_day = (min_per_day + max_per_day) / 2
        remaining_needed_for_min = max(0, min_per_day - today_count)

        debug_info["time_fraction"] = round(time_fraction, 3)
        debug_info["remaining_fraction"] = round(remaining_fraction, 3)
        debug_info["target_per_day"] = target_per_day

        # GUARANTEE ZONE: Last 20% of window, below minimum → force send
        # This ensures min_per_day is always met (barring system failures)
        guarantee_threshold = 0.20
        if remaining_fraction <= guarantee_threshold and remaining_needed_for_min > 0:
            debug_info["decision"] = "guarantee_zone"
            debug_info["remaining_needed_for_min"] = remaining_needed_for_min
            return True, debug_info

        # ADAPTIVE PROBABILITY: Based on remaining time and remaining target
        checks_per_hour = 60 / interval_minutes
        remaining_checks = max(1.0, remaining_fraction * window_hours * checks_per_hour)
        remaining_target = max(0.0, target_per_day - today_count)

        probability = remaining_target / remaining_checks

        # DEFICIT BOOST: If behind schedule based on TIME (not count ratio)
        # Expected count by now = target * time_fraction
        expected_by_now = target_per_day * time_fraction
        if today_count < expected_by_now and expected_by_now > 0:
            deficit_ratio = (expected_by_now - today_count) / expected_by_now
            # Boost up to 2x based on how far behind we are
            probability *= 1.0 + deficit_ratio

        # Clamp to [0, 1]
        probability = max(0.0, min(1.0, probability))

        debug_info["probability"] = round(probability, 4)
        debug_info["remaining_checks"] = round(remaining_checks, 1)
        debug_info["expected_by_now"] = round(expected_by_now, 2)

        roll = random.random()
        should_send = roll < probability

        debug_info["decision"] = "send" if should_send else "probabilistic_skip"
        debug_info["roll"] = round(roll, 4)

        return should_send, debug_info
