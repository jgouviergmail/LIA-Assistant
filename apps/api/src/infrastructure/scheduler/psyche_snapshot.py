"""
Scheduled task for weekly psyche narrative identity generation.

Generates a brief first-person self-narrative for each user with psyche enabled.
The narrative reflects on emotional tendencies, relationship quality, and confidence.

Note: psyche metrics history is recorded per-message in process_post_response
(psyche_history table, type "message"). No daily snapshots needed.

Runs weekly on Sundays at 03:00 UTC.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from src.core.config import settings
from src.core.constants import SCHEDULER_JOB_PSYCHE_DREAM_CYCLE
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.locks import SchedulerLock
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


async def process_psyche_weekly_narrative() -> dict[str, Any]:
    """Generate weekly narrative identity for all eligible users.

    Main entry point called by APScheduler. Uses distributed lock
    to prevent duplicate execution with multiple workers.

    Returns:
        Summary dict with count and duration.
    """
    if not settings.psyche_enabled:
        return {"skipped": True, "reason": "psyche disabled"}

    redis = await get_redis_cache()
    async with SchedulerLock(
        redis_client=redis,
        job_id=SCHEDULER_JOB_PSYCHE_DREAM_CYCLE,
        ttl_seconds=600,
    ) as acquired:
        if not acquired:
            logger.debug("psyche_narrative_lock_not_acquired")
            return {"skipped": True, "reason": "lock_not_acquired"}

        return await _generate_narratives()


async def _generate_narratives() -> dict[str, Any]:
    """Generate narrative identity for each user with psyche enabled.

    Returns:
        Summary dict with count and duration.
    """
    start = time.monotonic()
    count = 0

    try:
        from sqlalchemy import select

        from src.domains.auth.models import User
        from src.domains.psyche.models import PsycheState
        from src.domains.psyche.service import PsycheService
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            result = await db.execute(
                select(PsycheState.user_id)
                .join(User, User.id == PsycheState.user_id)
                .where(User.psyche_enabled.is_(True))
                .where(User.is_active.is_(True))
            )
            user_ids: list[UUID] = [row[0] for row in result.all()]

        for uid in user_ids:
            try:
                async with get_db_context() as db:
                    service = PsycheService(db)
                    await service.generate_and_save_narrative(user_id=uid)
                    await db.commit()
                    count += 1
            except Exception as e:
                logger.debug(
                    "psyche_narrative_generation_failed",
                    user_id=str(uid),
                    error=str(e),
                )

    except Exception as e:
        logger.warning(
            "psyche_weekly_narratives_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        return {"error": str(e)}

    duration_ms = round((time.monotonic() - start) * 1000)
    logger.info(
        "psyche_weekly_narratives_completed",
        narrative_count=count,
        duration_ms=duration_ms,
    )
    return {"count": count, "duration_ms": duration_ms}
