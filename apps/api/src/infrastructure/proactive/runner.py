"""
Proactive Task Runner - Generic Orchestrator.

Orchestrates execution of proactive tasks with:
- Batch processing of eligible users
- Eligibility checking (timezone, quota, cooldown, activity)
- Task-specific content generation
- Multi-channel notification dispatch
- Token and cost tracking
- Comprehensive metrics and logging

Pattern: Template Method + Strategy
- Template Method: execute() defines the algorithm skeleton
- Strategy: ProactiveTask implementations provide specific behavior

Usage:
    >>> from src.infrastructure.proactive import ProactiveTaskRunner
    >>> from src.domains.interests.proactive_task import InterestProactiveTask
    >>>
    >>> runner = ProactiveTaskRunner(
    ...     task=InterestProactiveTask(),
    ...     eligibility_checker=interest_eligibility_checker,
    ... )
    >>> stats = await runner.execute()

References:
    - Pattern: reminder_notification.py
"""

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.infrastructure.cache.pricing_cache import get_cached_cost_usd_eur
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics import (
    background_job_duration_seconds,
    background_job_errors_total,
)
from src.infrastructure.proactive.base import ProactiveTask, ProactiveTaskResult
from src.infrastructure.proactive.eligibility import EligibilityChecker
from src.infrastructure.proactive.notification import NotificationDispatcher, NotificationResult
from src.infrastructure.proactive.tracking import generate_proactive_run_id, track_proactive_tokens

logger = get_logger(__name__)


@dataclass
class RunnerStats:
    """
    Statistics from a proactive task runner execution.

    Invariant: processed == success + skipped + failed

    Attributes:
        processed: Number of users processed
        success: Number of successful notifications sent
        failed: Number of failures (content generation, dispatch, exceptions)
        skipped: Number of skipped users (not eligible, probabilistic, no target)
        duration_seconds: Total execution time
        skip_reasons: Breakdown of skip reasons
        failure_reasons: Breakdown of failure reasons
    """

    processed: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    duration_seconds: float = 0.0
    skip_reasons: dict[str, int] = field(default_factory=dict)
    failure_reasons: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for logging and metrics."""
        return {
            "processed": self.processed,
            "success": self.success,
            "failed": self.failed,
            "skipped": self.skipped,
            "duration_seconds": round(self.duration_seconds, 3),
            "skip_reasons": self.skip_reasons,
            "failure_reasons": self.failure_reasons,
        }

    def record_skip(self, reason: str) -> None:
        """Record a skip with reason."""
        self.skipped += 1
        self.skip_reasons[reason] = self.skip_reasons.get(reason, 0) + 1

    def record_failure(self, reason: str) -> None:
        """Record a failure with reason."""
        self.failed += 1
        self.failure_reasons[reason] = self.failure_reasons.get(reason, 0) + 1


class ProactiveTaskRunner:
    """
    Generic orchestrator for proactive tasks.

    Responsibilities:
    1. Iterate over eligible users (batch processing)
    2. Check common eligibility (timezone, quota, cooldown, activity)
    3. Delegate to task-specific eligibility and target selection
    4. Generate content via task implementation
    5. Dispatch notifications (FCM + SSE + archive)
    6. Track tokens and costs
    7. Report metrics

    Configuration:
        - batch_size: Users per batch (default 50)
        - max_retries: Retries per user on failure (default 3)
        - continue_on_error: Continue if one user fails (default True)

    Example:
        >>> runner = ProactiveTaskRunner(
        ...     task=InterestProactiveTask(),
        ...     eligibility_checker=EligibilityChecker(
        ...         task_type="interest",
        ...         enabled_field="interests_enabled",
        ...         ...
        ...     ),
        ... )
        >>> stats = await runner.execute()
        >>> print(f"Sent {stats.success} notifications")
    """

    def __init__(
        self,
        task: ProactiveTask,
        eligibility_checker: EligibilityChecker | None = None,
        dispatcher: NotificationDispatcher | None = None,
        batch_size: int = 50,
        max_retries: int = 3,
        continue_on_error: bool = True,
    ):
        """
        Initialize proactive task runner.

        Args:
            task: ProactiveTask implementation
            eligibility_checker: Optional eligibility checker (common checks)
            dispatcher: Optional notification dispatcher (defaults to new instance)
            batch_size: Users per batch (default 50)
            max_retries: Retries per user on failure (default 3)
            continue_on_error: Continue if one user fails (default True)
        """
        self.task = task
        self.eligibility_checker = eligibility_checker
        self.dispatcher = dispatcher or NotificationDispatcher()
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.continue_on_error = continue_on_error
        self.job_name = f"proactive_{task.task_type}"

    async def execute(self) -> RunnerStats:
        """
        Execute the proactive task for all eligible users.

        Main orchestration method that:
        1. Fetches eligible users in batches
        2. Processes each user through the full pipeline
        3. Tracks statistics and metrics
        4. Handles errors gracefully

        Returns:
            RunnerStats with execution statistics
        """
        start_time = time.perf_counter()
        stats = RunnerStats()

        try:
            from src.infrastructure.database.session import get_db_context

            async with get_db_context() as db:
                # Get eligible users (with locking to prevent concurrent processing)
                users = await self._get_eligible_users(db)

                if not users:
                    logger.debug(
                        "proactive_no_eligible_users",
                        task_type=self.task.task_type,
                    )
                    stats.duration_seconds = time.perf_counter() - start_time
                    self._record_metrics(stats)
                    return stats

                logger.info(
                    "proactive_batch_started",
                    task_type=self.task.task_type,
                    user_count=len(users),
                )

                # Process each user
                for user in users:
                    stats.processed += 1

                    try:
                        result = await self._process_user(user, db, stats)
                        if result:
                            stats.success += 1

                    except Exception as e:
                        stats.record_failure("unexpected_exception")
                        logger.error(
                            "proactive_user_failed",
                            task_type=self.task.task_type,
                            user_id=str(user.id),
                            error=str(e),
                            error_type=type(e).__name__,
                        )

                        if not self.continue_on_error:
                            raise

                # Final commit for any remaining changes (token tracking, etc.)
                await db.commit()

            # Record duration and metrics
            stats.duration_seconds = time.perf_counter() - start_time
            self._record_metrics(stats)

            logger.info(
                "proactive_batch_completed",
                task_type=self.task.task_type,
                **stats.to_dict(),
            )

            return stats

        except Exception as e:
            # Track error metric
            background_job_errors_total.labels(job_name=self.job_name).inc()

            # Record duration even on error
            stats.duration_seconds = time.perf_counter() - start_time
            background_job_duration_seconds.labels(job_name=self.job_name).observe(
                stats.duration_seconds
            )

            logger.error(
                "proactive_batch_failed",
                task_type=self.task.task_type,
                error=str(e),
                error_type=type(e).__name__,
                duration_seconds=round(stats.duration_seconds, 3),
            )
            raise

    async def _get_eligible_users(self, db: AsyncSession) -> list[Any]:
        """
        Get users eligible for this proactive task.

        Duplicate prevention is handled by:
        - APScheduler max_instances=1 (single job execution)
        - Cooldowns: global (2h) + per-topic (24h)

        Args:
            db: Database session

        Returns:
            List of User model instances
        """
        from src.domains.auth.models import User

        # Build query for active users
        # Task-specific filtering (e.g., interests_enabled) is handled by eligibility checker
        # Note: No FOR UPDATE needed - duplicates prevented by:
        # - APScheduler max_instances=1 per job
        # - Cooldowns (global + per-topic)
        query = (
            select(User)
            .where(
                User.is_verified == True,  # noqa: E712 - SQLAlchemy requires ==
                User.is_active == True,  # noqa: E712
                User.deleted_at.is_(None),
            )
            .limit(self.batch_size)
        )

        result = await db.execute(query)
        return list(result.scalars().all())

    async def _process_user(self, user: Any, db: AsyncSession, stats: RunnerStats) -> bool:
        """
        Process a single user through the proactive task pipeline.

        Pipeline:
        1. Check common eligibility (timezone, quota, cooldown, activity)
        2. Check task-specific eligibility
        3. Select target (interest, event, etc.)
        4. Generate content
        5. Dispatch notification
        6. Track tokens
        7. Call task's on_notification_sent hook

        Args:
            user: User model instance
            db: Database session
            stats: RunnerStats to record skip/failure reasons

        Returns:
            True if notification was sent, False otherwise
        """
        now = datetime.now(UTC)
        user_settings = self._extract_user_settings(user)

        # Lazy import to avoid circular deps; isolated behind a helper so metric
        # failures never break the business logic.
        def _record_eligibility(result: str) -> None:
            try:
                from src.infrastructure.observability.metrics_registry import (
                    proactive_eligibility_check_total,
                )

                proactive_eligibility_check_total.labels(
                    task_type=self.task.task_type, result=result
                ).inc()
            except Exception:
                pass

        # 0. Usage limit check (Layer 3) — centralized via is_user_blocked_for_llm
        from src.domains.usage_limits.service import UsageLimitService

        if await UsageLimitService.is_user_blocked_for_llm(
            user.id,
            layer="proactive",
            context_log_event="proactive_user_usage_blocked",
            extra_log_fields={"task_type": self.task.task_type},
        ):
            stats.record_skip("usage_limit_exceeded")
            _record_eligibility("usage_limit_exceeded")
            return False

        # 1. Common eligibility checks
        if self.eligibility_checker:
            eligibility = await self.eligibility_checker.check(user, db, now)
            if not eligibility.eligible:
                logger.debug(
                    "proactive_user_not_eligible",
                    task_type=self.task.task_type,
                    user_id=str(user.id),
                    reason=eligibility.reason.value,
                    details=eligibility.details,
                )
                stats.record_skip(eligibility.reason.value)
                _record_eligibility(eligibility.reason.value)
                return False

            # 1b. Probabilistic check: should we send now?
            # Time-aware algorithm with guaranteed minimum delivery.
            today_count = await self._get_today_notification_count(user, db, now)

            start_hour_field = self.eligibility_checker.start_hour_field
            end_hour_field = self.eligibility_checker.end_hour_field
            start_hour = getattr(user, start_hour_field, 9)
            end_hour = getattr(user, end_hour_field, 22)
            window_hours = (
                end_hour - start_hour if end_hour > start_hour else 24 - start_hour + end_hour
            )

            # Calculate elapsed hours in the user's notification window
            elapsed_hours = self._calculate_elapsed_hours(user, now, start_hour, window_hours)

            should_send, debug_info = self.eligibility_checker.should_send_notification(
                user=user,
                today_count=today_count,
                window_hours=window_hours,
                elapsed_hours=elapsed_hours,
                interval_minutes=self.eligibility_checker.interval_minutes,
            )

            if not should_send:
                logger.info(
                    "proactive_probabilistic_decision",
                    task_type=self.task.task_type,
                    user_id=str(user.id),
                    **debug_info,
                )
                stats.record_skip("probabilistic_skip")
                _record_eligibility("probabilistic_skip")
                return False

            logger.info(
                "proactive_probabilistic_decision",
                task_type=self.task.task_type,
                user_id=str(user.id),
                **debug_info,
            )

        # 2. Task-specific eligibility
        if not await self.task.check_eligibility(user.id, user_settings, now):
            logger.debug(
                "proactive_task_eligibility_failed",
                task_type=self.task.task_type,
                user_id=str(user.id),
            )
            stats.record_skip("task_eligibility_failed")
            _record_eligibility("task_eligibility_failed")
            return False

        # Eligibility passed all checks
        _record_eligibility("eligible")

        # 3. Select target
        target = await self.task.select_target(user.id)
        if target is None:
            logger.debug(
                "proactive_no_target",
                task_type=self.task.task_type,
                user_id=str(user.id),
            )
            stats.record_skip("no_target")
            return False

        # 4. Generate content
        user_language = (
            getattr(user, "language", settings.default_language) or settings.default_language
        )
        result = await self.task.generate_content(user.id, target, user_language)

        if not result.success or not result.content:
            logger.warning(
                "proactive_content_generation_failed",
                task_type=self.task.task_type,
                user_id=str(user.id),
                target_id=result.target_id,
                error=result.error,
            )
            stats.record_failure("content_generation_failed")
            return False

        # Track content source (wikipedia, perplexity, llm_reflection, etc.).
        # `source_name` is an optional attribute on task-specific result subclasses —
        # use getattr() so tasks that don't populate it (or test fakes) don't break.
        _source_name = getattr(result, "source_name", None)
        if _source_name:
            try:
                from src.infrastructure.observability.metrics_registry import (
                    proactive_content_source_total,
                )

                proactive_content_source_total.labels(
                    task_type=self.task.task_type, source=_source_name
                ).inc()
            except Exception:
                pass

        # 4b. Pre-generate run_id and compute cost for metadata injection.
        # This ensures the archived message contains run_id + token data
        # BEFORE track_proactive_tokens() runs, fixing the LEFT JOIN in
        # get_messages_with_token_summaries() for history queries.
        target_id_for_tracking = result.target_id or str(getattr(target, "id", "unknown"))
        run_id = generate_proactive_run_id(self.task.task_type, target_id_for_tracking)

        cost_eur = 0.0
        if result.model_name:
            try:
                _, cost_eur = get_cached_cost_usd_eur(
                    model=result.model_name,
                    prompt_tokens=result.tokens_in,
                    completion_tokens=result.tokens_out,
                    cached_tokens=result.tokens_cache,
                )
            except Exception:
                logger.debug(
                    "proactive_cost_pre_calculation_fallback",
                    task_type=self.task.task_type,
                    user_id=str(user.id),
                )

        # Inject standard token tracking data into metadata (centralized, DRY).
        # All proactive types get token display in chat bubbles automatically.
        result.metadata.update(
            {
                "run_id": run_id,
                "tokens_in": result.tokens_in,
                "tokens_out": result.tokens_out,
                "tokens_cache": result.tokens_cache,
                "cost_eur": cost_eur,
                "model_name": result.model_name,
            }
        )

        # 5. Dispatch notification
        # Resolve push_enabled by convention: user field "{task_type}_push_enabled"
        push_enabled = getattr(user, f"{self.task.task_type}_push_enabled", True)
        notification_result = await self._dispatch_notification(
            user=user,
            result=result,
            target=target,
            db=db,
            push_enabled=push_enabled,
            run_id=run_id,
        )

        if not notification_result.success:
            logger.warning(
                "proactive_notification_dispatch_failed",
                task_type=self.task.task_type,
                user_id=str(user.id),
                target_id=result.target_id,
                error=notification_result.error,
            )
            stats.record_failure("dispatch_failed")
            return False

        # Track per-channel notification delivery + tokens/cost (dashboard 13).
        # Failures here must never break the proactive pipeline.
        try:
            from src.infrastructure.observability.metrics_registry import (
                track_proactive_notification,
            )
            from src.infrastructure.observability.metrics_registry import (
                track_proactive_tokens as metric_track_proactive_tokens,
            )

            track_proactive_notification(
                task_type=self.task.task_type,
                fcm_sent=notification_result.fcm_success > 0,
                sse_sent=notification_result.sse_sent,
                archived=notification_result.archived,
            )
            metric_track_proactive_tokens(
                task_type=self.task.task_type,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                tokens_cache=result.tokens_cache,
                cost_eur=cost_eur,
            )
        except Exception:
            pass

        # 6. Track tokens (autonomous transaction - each component manages its own)
        tracked_run_id = await track_proactive_tokens(
            user_id=user.id,
            task_type=self.task.task_type,
            target_id=target_id_for_tracking,
            conversation_id=notification_result.conversation_id,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            tokens_cache=result.tokens_cache,
            model_name=result.model_name,
            run_id=run_id,
        )

        # 7. Call task's on_notification_sent hook
        try:
            await self.task.on_notification_sent(user.id, target, result)
        except Exception as e:
            # Non-fatal: log but continue
            logger.warning(
                "proactive_on_notification_sent_failed",
                task_type=self.task.task_type,
                user_id=str(user.id),
                error=str(e),
            )

        logger.info(
            "proactive_notification_sent",
            task_type=self.task.task_type,
            user_id=str(user.id),
            target_id=result.target_id,
            source=result.source_name,
            tokens_total=result.total_tokens,
            run_id=tracked_run_id or run_id,
        )

        return True

    async def _dispatch_notification(
        self,
        user: Any,
        result: ProactiveTaskResult,
        target: Any,
        db: AsyncSession,
        push_enabled: bool = True,
        run_id: str | None = None,
    ) -> NotificationResult:
        """
        Dispatch notification via all channels.

        Args:
            user: User model instance
            result: Content generation result
            target: Task target (interest, event, etc.)
            db: Database session
            push_enabled: Whether to send push notifications (FCM/Telegram).
                When False, only archive + SSE are used.
            run_id: Pre-generated run_id for token tracking linkage.
                Passed to dispatcher for inclusion in archived message metadata.

        Returns:
            NotificationResult with dispatch status
        """
        # Extract target_id for tracking
        target_id = result.target_id
        if not target_id:
            # Try to get ID from target object
            target_id = str(getattr(target, "id", "unknown"))

        return await self.dispatcher.dispatch(
            user=user,
            content=result.content or "",
            task_type=self.task.task_type,
            target_id=target_id,
            metadata=result.metadata,
            db=db,
            push_enabled=push_enabled,
            run_id=run_id,
        )

    @staticmethod
    def _calculate_elapsed_hours(
        user: Any,
        now: datetime,
        start_hour: int,
        window_hours: int,
    ) -> float:
        """
        Calculate hours elapsed since the start of the user's notification window.

        Handles timezone conversion and overnight windows (e.g., 22-9).

        Args:
            user: User model instance (for timezone)
            now: Current datetime in UTC
            start_hour: Window start hour in user timezone
            window_hours: Total window duration in hours

        Returns:
            Hours elapsed since window start (clamped to [0, window_hours])
        """
        from zoneinfo import ZoneInfo

        user_tz_str = getattr(user, "timezone", None) or "UTC"
        try:
            user_tz = ZoneInfo(user_tz_str)
        except (KeyError, ValueError):
            user_tz = ZoneInfo("UTC")

        user_now = now.astimezone(user_tz)
        current_hour_float = user_now.hour + user_now.minute / 60.0

        # Calculate elapsed since start_hour (handles overnight wrapping)
        elapsed = current_hour_float - start_hour
        if elapsed < 0:
            elapsed += 24  # Overnight window: current time is past midnight

        # Clamp to [0, window_hours]
        return max(0.0, min(elapsed, float(window_hours)))

    def _extract_user_settings(self, user: Any) -> dict[str, Any]:
        """
        Extract user settings as dict for task eligibility check.

        Args:
            user: User model instance

        Returns:
            Dict with relevant user settings
        """
        # Extract common settings that tasks might need
        settings: dict[str, Any] = {}

        # Common fields
        for field_name in [
            "language",
            "timezone",
            "interests_enabled",
            "interests_notify_start_hour",
            "interests_notify_end_hour",
            "interests_notify_min_per_day",
            "interests_notify_max_per_day",
            # Heartbeat fields
            "heartbeat_enabled",
            "heartbeat_min_per_day",
            "heartbeat_max_per_day",
            "heartbeat_push_enabled",
            "heartbeat_notify_start_hour",
            "heartbeat_notify_end_hour",
        ]:
            if hasattr(user, field_name):
                settings[field_name] = getattr(user, field_name)

        return settings

    async def _get_today_notification_count(
        self,
        user: Any,
        db: AsyncSession,
        now: datetime,
    ) -> int:
        """
        Get count of notifications sent today for this user.

        Uses the eligibility checker's notification model if available.

        Args:
            user: User model instance
            db: Database session
            now: Current datetime

        Returns:
            Number of notifications sent today
        """
        if not self.eligibility_checker or not self.eligibility_checker.notification_model:
            return 0

        from datetime import timezone
        from zoneinfo import ZoneInfo

        from sqlalchemy import func, select

        # Get user timezone for "today" calculation
        user_tz_str = getattr(user, "timezone", None) or "UTC"
        try:
            user_tz: ZoneInfo | timezone = ZoneInfo(user_tz_str)
        except (KeyError, ValueError):
            from datetime import UTC

            user_tz = UTC

        # Calculate start of today in user's timezone
        user_now = now.astimezone(user_tz)
        today_start = datetime(
            user_now.year, user_now.month, user_now.day, tzinfo=user_tz
        ).astimezone(user_tz)

        # Convert to UTC for query
        from datetime import UTC

        today_start_utc = today_start.astimezone(UTC)

        # Count notifications sent today
        model = self.eligibility_checker.notification_model
        query = select(func.count()).where(
            model.user_id == user.id,
            model.created_at >= today_start_utc,
        )
        result = await db.execute(query)
        return result.scalar() or 0

    def _record_metrics(self, stats: RunnerStats) -> None:
        """
        Record Prometheus metrics for this execution.

        Emits both the generic background_job_duration_seconds (for cross-job comparison)
        and the domain-specific proactive_task_* metrics (for dashboard 13 panels).
        """
        # Generic job duration (for dashboard 06 / background jobs)
        background_job_duration_seconds.labels(job_name=self.job_name).observe(
            stats.duration_seconds
        )

        # Domain-specific proactive metrics (dashboard 13)
        try:
            from src.infrastructure.observability.metrics_registry import (
                track_proactive_task_execution,
            )

            track_proactive_task_execution(
                task_type=self.task.task_type,
                processed=stats.processed,
                success=stats.success,
                failed=stats.failed,
                skipped=stats.skipped,
                duration_seconds=stats.duration_seconds,
            )

        except ImportError:
            # Metrics not yet defined, skip
            logger.debug(
                "proactive_metrics_not_available",
                task_type=self.task.task_type,
            )


async def execute_proactive_task(
    task: ProactiveTask,
    eligibility_checker: EligibilityChecker | None = None,
    batch_size: int = 50,
) -> RunnerStats:
    """
    Convenience function to execute a proactive task.

    Creates a runner and executes the task. Useful for scheduler jobs.

    Args:
        task: ProactiveTask implementation
        eligibility_checker: Optional eligibility checker
        batch_size: Users per batch

    Returns:
        RunnerStats with execution statistics

    Example:
        >>> # In scheduler job
        >>> async def process_interest_notifications():
        ...     return await execute_proactive_task(
        ...         task=InterestProactiveTask(),
        ...         eligibility_checker=interest_checker,
        ...     )
    """
    runner = ProactiveTaskRunner(
        task=task,
        eligibility_checker=eligibility_checker,
        batch_size=batch_size,
    )
    return await runner.execute()
