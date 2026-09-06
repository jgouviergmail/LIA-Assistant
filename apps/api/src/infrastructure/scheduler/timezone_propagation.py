"""Moving a reader's clock moves everything they scheduled on a wall clock.

Two domains answer that question — routines and reminders — and the profile
update that asks it lives in a third. Calling them from `users` directly closed
a domain-to-domain cycle (`reminders<->users`, F009): the reminders router
imports `User` for its session dependency, so the edge back was already there
and the ratchet is shrink-only, tolerated twins notwithstanding.

The composition therefore sits in `infrastructure`, which is where this
codebase already orchestrates across domains for exactly this reason — see the
note on `condition_evaluators.py` in `scheduled_actions/models.py`.

**One block, not two.** The reminders were missing from the profile update
until 2026-09-06: correct while their instant was frozen at creation, wrong the
moment they gained a wall clock. A second call site elsewhere would be a second
place to remember, so both surfaces move here, together, or the omission
happens again.
"""

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


async def propagate_timezone(db: AsyncSession, user_id: UUID, new_timezone: str) -> dict[str, int]:
    """Move every schedule the reader owns to their new zone.

    Each surface is independently best-effort, and independence here has to be
    TRANSACTIONAL, not merely a caught exception: a failed statement poisons a
    PostgreSQL transaction, so a reminder whose flush failed would take the
    routines just moved — and the profile update that triggered all of this —
    down with it on the caller's commit. Each surface therefore runs inside its
    own savepoint, the way `scheduled_actions/runs.py` writes its history.

    Args:
        db: The session the caller will commit.
        user_id: The reader who moved.
        new_timezone: Their new IANA zone.

    Returns:
        How many rows each surface moved, keyed by surface name. An absent key
        means that surface failed and said so in the log.
    """
    from src.domains.reminders.service import ReminderService
    from src.domains.scheduled_actions.service import ScheduledActionService

    moved: dict[str, int] = {}
    for surface, service in (
        ("scheduled_actions", ScheduledActionService(db)),
        ("reminders", ReminderService(db)),
    ):
        try:
            async with db.begin_nested():
                moved[surface] = await service.recalculate_all_for_user(user_id, new_timezone)
        except Exception as exc:
            logger.warning(
                "timezone_recalculation_failed",
                surface=surface,
                user_id=str(user_id),
                error=str(exc),
            )
    return moved
