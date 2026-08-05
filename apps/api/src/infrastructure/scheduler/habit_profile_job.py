"""Nightly recompute of learned habit profiles (ADR-214).

One leader-elected run per night: iterate enabled users, recompute each
rhythm profile from the aggregated conversation history and sync the
ACTIVE_WINDOW habit rows. Each user gets his OWN session (an AsyncSession is
never shared across tasks) and his own error boundary — one failing user
never starves the rest.

RPi5 budget: the per-user work is one SQL aggregate (~168 rows) + one
UPSERT; users with no new messages and nothing left to decay are skipped
(delta rule owned by the service).
"""

from __future__ import annotations

import time
from contextlib import suppress

from sqlalchemy import select

from src.core.config import settings
from src.infrastructure.database import get_db_context
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_habits import (
    habit_profile_job_seconds,
    habit_profile_users_total,
)

logger = get_logger(__name__)


def _record_outcome(outcome: str) -> None:
    """Count one per-user outcome (best-effort — never breaks the job)."""
    with suppress(Exception):
        habit_profile_users_total.labels(outcome=outcome).inc()


async def run_habit_profile_job() -> None:
    """Recompute every enabled user's rhythm profile (nightly)."""
    if not getattr(settings, "habits_enabled", False):
        return

    from src.domains.users.models import User

    started = time.monotonic()
    processed = 0
    errors = 0

    # Snapshot the candidate user ids first, in a short-lived session — the
    # per-user work then opens its own session so no session ever spans users.
    async with get_db_context() as db:
        result = await db.execute(
            select(User.id).where(
                User.is_active == True,  # noqa: E712 — SQLAlchemy binary expression
                User.deleted_at.is_(None),
                User.habits_enabled == True,  # noqa: E712
            )
        )
        user_ids = [row[0] for row in result.all()]

    for user_id in user_ids:
        try:
            async with get_db_context() as db:
                from src.domains.habits.service import HabitsService
                from src.domains.users.models import User as UserModel

                user = await db.get(UserModel, user_id)
                if user is None or not user.habits_enabled:
                    _record_outcome("skipped_user_disabled")
                    continue
                service = HabitsService(db)
                outcome = await service.recompute_user_profile(user)
                await db.commit()
                _record_outcome(outcome)
                processed += 1
        except Exception as exc:  # noqa: BLE001 — one user must not starve the rest
            errors += 1
            _record_outcome("error")
            logger.error(
                "habit_profile_user_failed",
                user_id=str(user_id),
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )

    duration = time.monotonic() - started
    with suppress(Exception):
        habit_profile_job_seconds.observe(duration)
    logger.info(
        "habit_profile_job_completed",
        users_considered=len(user_ids),
        users_processed=processed,
        errors=errors,
        duration_seconds=round(duration, 2),
    )
