"""
Scheduled task for periodic journal consolidation.

Runs every N hours (configurable) to review and maintain journal entries
for eligible users. The assistant autonomously manages its own journals.

Simplified pattern compared to heartbeat (no ProactiveTaskRunner/EligibilityChecker).
Uses SchedulerLock for multi-worker safety.

Flow for each eligible user:
1. Load personality instruction + code
2. Call consolidate_journals_for_user()
3. Track metrics (duration, errors, actions)

Eligibility:
- journals_enabled = True AND journal_consolidation_enabled = True
- At least journal_consolidation_min_entries active entries
- Last consolidation > cooldown OR never consolidated
"""

import time
from datetime import UTC, datetime, timedelta
from typing import Any

from src.core.config import settings
from src.core.constants import SCHEDULER_JOB_JOURNAL_CONSOLIDATION
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.locks import SchedulerLock
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_journals import (
    journal_level_distribution,
    journal_portrait_age_hours,
    journal_theme_distribution,
    journal_zero_injection_age_days,
)

logger = get_logger(__name__)


async def _refresh_effectiveness_gauge() -> None:
    """Refresh the journal effectiveness gauges after a consolidation batch.

    - ``journal_zero_injection_age_days``: average age (in days) of active entries
      never injected into a prompt. Central effectiveness metric — high values
      signal directives accumulating without value.
    - ``journal_level_distribution{level}``: count of active entries per
      abstraction level (L0/L1/L2/L3). Reveals the cognitive shape of the
      journal — too many L0 means insufficient maturation, too many L1 with
      no L2 means missing pattern synthesis.
    - ``journal_theme_distribution{theme}``: count of active entries per theme.
      A theme flat at zero is an unreachable theme, not a quiet one.
    - ``journal_portrait_age_hours``: age of the oldest compiled portrait —
      rises when a user's consolidation has stalled.

    Best-effort: never raises, never blocks the consolidation flow.
    """
    try:
        from src.domains.journals.models import JournalTheme
        from src.domains.journals.repository import JournalEntryRepository
        from src.infrastructure.database import get_db_context

        async with get_db_context() as db:
            repo = JournalEntryRepository(db)
            avg_days = await repo.compute_zero_injection_age_days_avg()
            level_counts = await repo.count_by_level_global()
            theme_counts = await repo.count_by_theme_global()
            portrait_age = await repo.compute_max_portrait_age_hours()
        journal_zero_injection_age_days.set(avg_days)
        # Reset all known level labels to 0 (so absent levels report 0, not stale)
        for known_level in ("L0", "L1", "L2", "L3"):
            journal_level_distribution.labels(level=known_level).set(
                level_counts.get(known_level, 0)
            )
        # Same for themes — an absent theme must read 0, which is the alertable
        # value, not "no series".
        for theme in JournalTheme:
            journal_theme_distribution.labels(theme=theme.value).set(
                theme_counts.get(theme.value, 0)
            )
        journal_portrait_age_hours.set(portrait_age)
        logger.debug(
            "journal_effectiveness_gauges_refreshed",
            avg_days=round(avg_days, 2),
            level_counts=level_counts,
            theme_counts=theme_counts,
            portrait_age_hours=round(portrait_age, 1),
        )
    except Exception as exc:
        logger.warning(
            "journal_effectiveness_gauges_refresh_failed",
            error=str(exc),
        )


async def process_journal_consolidation() -> dict[str, Any]:
    """
    Process journal consolidation for all eligible users.

    Main entry point called by APScheduler. Uses distributed lock
    to prevent duplicate execution with multiple workers.

    Returns:
        Stats dict with processed/skipped/errored counts
    """
    start_time = time.monotonic()

    redis = await get_redis_cache()
    async with SchedulerLock(redis, SCHEDULER_JOB_JOURNAL_CONSOLIDATION) as lock:
        if not lock.acquired:
            logger.debug("journal_consolidation_lock_busy")
            return {"status": "skipped", "reason": "lock_busy"}

        logger.info("journal_consolidation_started")

        users_processed = 0
        users_errored = 0
        total_actions = 0

        try:
            from src.infrastructure.database import get_db_context

            async with get_db_context() as db:
                from sqlalchemy import and_, func, select

                from src.domains.journals.models import JournalEntry, JournalEntryStatus
                from src.domains.users.models import User

                # Calculate cooldown threshold
                cooldown_threshold = datetime.now(UTC) - timedelta(
                    hours=settings.journal_consolidation_cooldown_hours
                )
                min_entries = settings.journal_consolidation_min_entries

                # Subquery: count active entries per user
                active_count_subq = (
                    select(
                        JournalEntry.user_id,
                        func.count(JournalEntry.id).label("entry_count"),
                    )
                    .where(JournalEntry.status == JournalEntryStatus.ACTIVE.value)
                    .group_by(JournalEntry.user_id)
                    .having(func.count(JournalEntry.id) >= min_entries)
                    .subquery()
                )

                # Query eligible users
                eligible_query = (
                    select(User)
                    .join(active_count_subq, User.id == active_count_subq.c.user_id)
                    .where(
                        and_(
                            User.journals_enabled.is_(True),
                            User.journal_consolidation_enabled.is_(True),
                            User.is_active.is_(True),
                            User.deleted_at.is_(None),
                            # Cooldown: never consolidated OR last > cooldown
                            (
                                User.journal_last_consolidated_at.is_(None)
                                | (User.journal_last_consolidated_at < cooldown_threshold)
                            ),
                        )
                    )
                )

                db_result = await db.execute(eligible_query)
                eligible_users = list(db_result.scalars().all())

            logger.info(
                "journal_consolidation_eligible_users",
                count=len(eligible_users),
            )

            # Process each eligible user
            for user in eligible_users:
                try:
                    # 0. Usage limit pre-check (skip early before any DB/LLM work)
                    from src.domains.usage_limits.service import UsageLimitService

                    if await UsageLimitService.is_user_blocked_for_llm(
                        user.id,
                        layer="journal_consolidation",
                    ):
                        continue

                    # Load personality
                    personality_instruction = None
                    personality_code = None

                    async with get_db_context() as db:
                        if user.personality_id:
                            from src.domains.personalities.service import PersonalityService

                            ps = PersonalityService(db)
                            personality = await ps.get_by_id(user.personality_id)
                            if personality:
                                personality_instruction = personality.prompt_instruction
                                personality_code = personality.code

                    # Run consolidation
                    from src.domains.journals.consolidation_service import (
                        consolidate_journals_for_user,
                    )

                    actions = await consolidate_journals_for_user(
                        user_id=user.id,
                        personality_instruction=personality_instruction,
                        personality_code=personality_code,
                        user_language=getattr(user, "language", settings.default_language),
                        consolidation_with_history=user.journal_consolidation_with_history,
                        max_total_chars=user.journal_max_total_chars,
                        max_entry_chars=user.journal_max_entry_chars,
                        last_consolidated_at=user.journal_last_consolidated_at,
                    )

                    users_processed += 1
                    total_actions += actions

                except Exception as e:
                    users_errored += 1
                    logger.error(
                        "journal_consolidation_user_failed",
                        user_id=str(user.id),
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    continue

        except Exception as e:
            status = "error"
            logger.error(
                "journal_consolidation_batch_failed",
                error=str(e),
                exc_info=True,
            )
        else:
            status = "completed"

        # Refresh the effectiveness gauge after the batch (best-effort).
        # Captures the post-consolidation state of "stale" entries.
        await _refresh_effectiveness_gauge()

        duration_ms = (time.monotonic() - start_time) * 1000

        result: dict[str, Any] = {
            "status": status,
            "users_processed": users_processed,
            "users_errored": users_errored,
            "total_actions": total_actions,
            "duration_ms": round(duration_ms, 1),
        }

        logger.info(
            "journal_consolidation_finished",
            **result,
        )

        return result
