"""How often a person uses a skill — ONE door, one atomic count per run (lot 14).

A turn uses a skill when the response node activates the one it settled on, or
when the ReAct loop activates one itself (``activate_skill_tool``). A run reports
a skill ONCE at the source — the loop's first activation, or the response node
when the loop did not activate it (``react_activated_skills``) — and the run's
identity is the second net: ``use_count`` moves by ``last_used_run_id IS
DISTINCT FROM :run`` in the very statement that stamps the run — server-side
arithmetic, never a read then a write. The name resolves as the turn resolves
it, the person's own skill before a system skill of that name, and only the
person's own state moves.

The count is a record, never a reason for a turn to wait or fail: it is written
off the turn's path (``schedule_skill_use``), on a short session of its own, and
a failure is logged with its facts.

What the count is for: a skill left active and unused still enters the
analyzer's list on every turn. ``is_dormant`` names the ones unused for
``SKILLS_DORMANT_AFTER_DAYS`` of COUNTING (``usage_counted_since``: nothing
was counted before the migration), so the settings can propose switching them
off; ``settle_dormant`` is the one door the person's answer goes through.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import and_, case, exists, func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.skills.models import Skill, UserSkillState
from src.domains.skills.personal_state import personal_state
from src.domains.skills.preference_service import SkillPreferenceService
from src.domains.skills.previous_version import restorable_at
from src.domains.skills.ui_projection import merge_skill_metadata
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.database.errors import database_error_fields
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


async def record_skill_use(user_id: UUID, skill_name: str, *, run_id: str) -> None:
    """Count one run's use of a skill on the person's own state.

    Args:
        user_id: The person the run served.
        skill_name: The skill as the turn named it.
        run_id: The run; a second report of the same run counts nothing.
    """
    own = select(Skill.id).where(Skill.owner_id == user_id, Skill.name == skill_name)
    resolved = select(Skill.id).where(
        Skill.name == skill_name,
        or_(Skill.owner_id == user_id, and_(Skill.is_system.is_(True), ~exists(own))),
    )
    fresh = UserSkillState.last_used_run_id.is_distinct_from(run_id)
    statement = (
        update(UserSkillState)
        .where(UserSkillState.user_id == user_id, UserSkillState.skill_id.in_(resolved))
        .values(
            use_count=UserSkillState.use_count + case((fresh, 1), else_=0),
            last_used_at=func.now(),
            last_used_run_id=run_id,
        )
        .execution_options(synchronize_session=False)
    )
    try:
        async with get_db_context() as db:
            await db.execute(statement)
    except SQLAlchemyError as error:
        logger.warning(
            "skill_use_record_failed",
            user_id=str(user_id),
            run_id=run_id,
            **database_error_fields(error),
        )


def schedule_skill_use(user_id: UUID, skill_name: str, *, run_id: str) -> None:
    """Count the use off the turn's path: the turn neither waits for it nor fails with it."""
    safe_fire_and_forget(
        record_skill_use(user_id, skill_name, run_id=run_id),
        name="skill_use_record",
        independent_of_graph=True,
    )


def is_dormant(
    *,
    is_active: bool,
    always_loaded: bool,
    last_used_at: datetime | None,
    counted_since: datetime,
    kept_at: datetime | None,
    now: datetime,
    after_days: int,
) -> bool:
    """Whether an active skill went unused long enough to propose switching it off.

    Args:
        is_active: The person's toggle; an inactive skill is never dormant.
        always_loaded: Its instructions enter every turn with no activation to
            count, so its use cannot be observed: never dormant.
        last_used_at: The last run that used it, or None.
        counted_since: When counting began for this state (the migration for
            a state that existed before it, the state's creation otherwise): a
            skill with no use recorded is measured from there, never from a
            past nobody counted.
        kept_at: When the person last chose to keep it after the proposal: the
            proposal waits a whole period again, never asks twice in a row.
        now: The present instant.
        after_days: ``SKILLS_DORMANT_AFTER_DAYS``.

    Returns:
        True when it is active, observable, and nothing used or kept it in the
        last ``after_days`` days of counting.
    """
    if not is_active or always_loaded:
        return False
    horizon = now - timedelta(days=after_days)
    latest = max(moment for moment in (last_used_at, counted_since, kept_at) if moment)
    return latest <= horizon


def usage_view(
    listed: dict[str, Any], *, always_loaded: bool, now: datetime, after_days: int
) -> dict[str, Any]:
    """What the settings show of a listed skill's use: the count since when, the last use, the verdict.

    Args:
        listed: One entry of ``SkillPreferenceService.get_user_visible_skills``.
        always_loaded: The skill's declaration, read from its cached metadata.
        now: The present instant.
        after_days: ``SKILLS_DORMANT_AFTER_DAYS``, published beside the list.

    Returns:
        ``use_count``, ``last_used_at``, ``counted_since`` (the count's start,
        stated so a count is never read as « ever ») and ``dormant``.
    """
    return {
        "use_count": listed["use_count"],
        "last_used_at": listed["last_used_at"],
        "counted_since": listed["counted_since"],
        "dormant": is_dormant(
            is_active=listed["is_active"],
            always_loaded=always_loaded,
            last_used_at=listed["last_used_at"],
            counted_since=listed["counted_since"],
            kept_at=listed["dormancy_kept_at"],
            now=now,
            after_days=after_days,
        ),
    }


def skill_life(
    listed: dict[str, Any],
    *,
    always_loaded: bool,
    previous: dict[str, datetime],
    now: datetime,
    after_days: int,
) -> dict[str, Any]:
    """What the settings AND the assistant say of a listed skill's life: its use and its way back.

    Args:
        listed: One entry of ``SkillPreferenceService.get_user_visible_skills``.
        always_loaded: The skill's declaration, read from its cached metadata.
        previous: ``previous_versions`` of the person.
        now: The present instant.
        after_days: ``SKILLS_DORMANT_AFTER_DAYS``.

    Returns:
        :func:`usage_view` plus ``previous_version_at``.
    """
    return {
        **usage_view(listed, always_loaded=always_loaded, now=now, after_days=after_days),
        "previous_version_at": restorable_at(listed, previous),
    }


class DormantDecision(StrEnum):
    """The person's answer to the dormant-skills proposal."""

    #: Switch them off: they leave the analyzer's list.
    SWITCH_OFF = "switch_off"
    #: Keep them on: the proposal waits a whole period again.
    KEEP = "keep"


async def settle_dormant(
    db: AsyncSession,
    user_id: UUID,
    skill_ids: Sequence[UUID],
    *,
    decision: DormantDecision,
    now: datetime,
    after_days: int,
) -> list[str]:
    """Apply the person's answer to the skills the proposal showed, if they are still dormant.

    The verdict is taken again on the state LOCKED for the write: a skill used
    since the screen was drawn is left as it is, and a skill the screen never
    showed is never touched — the person decided about the list they saw.
    Answering twice settles nothing the second time.

    Args:
        db: The request's session; the caller commits.
        user_id: The person.
        skill_ids: The skills the proposal showed.
        decision: Switch them off, or keep them on.
        now: The present instant (a kept skill is kept from it).
        after_days: ``SKILLS_DORMANT_AFTER_DAYS``.

    Returns:
        The names settled, in the order asked.
    """
    visible = {
        row["skill_id"]: row
        for row in await SkillPreferenceService(db).get_user_visible_skills(user_id)
    }
    asked = list(dict.fromkeys(skill_ids))
    settled_ids: set[UUID] = set()
    # One canonical lock order: two answers naming the same skills in another
    # order would otherwise each hold a lock the other waits for.
    for skill_id in sorted(asked, key=str):
        listed = visible.get(str(skill_id))
        if listed is None:
            continue
        try:
            state = await personal_state(db, user_id, skill_id)
        except ValueError:
            # Deleted or hidden between the read and the lock: nothing left to settle.
            continue
        if not is_dormant(
            is_active=state.is_active,
            always_loaded=merge_skill_metadata(listed)["always_loaded"],
            last_used_at=state.last_used_at,
            counted_since=state.usage_counted_since,
            kept_at=state.dormancy_kept_at,
            now=now,
            after_days=after_days,
        ):
            continue
        if decision is DormantDecision.SWITCH_OFF:
            state.is_active = False
        else:
            state.dormancy_kept_at = now
        settled_ids.add(skill_id)
    await db.flush()
    settled = [visible[str(skill_id)]["name"] for skill_id in asked if skill_id in settled_ids]
    logger.info(
        "skills_dormant_settled", user_id=str(user_id), decision=decision.value, count=len(settled)
    )
    return settled


__all__ = [
    "DormantDecision",
    "is_dormant",
    "record_skill_use",
    "schedule_skill_use",
    "settle_dormant",
    "skill_life",
    "usage_view",
]
