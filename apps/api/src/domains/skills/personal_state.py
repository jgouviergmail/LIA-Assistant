"""Fresh exact personal skill state, shared by original toggles and native explicit changes."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.skills.models import Skill, UserSkillState


async def personal_state(db: AsyncSession, actor_id: UUID, skill_id: UUID) -> UserSkillState:
    skill = await db.scalar(
        select(Skill)
        .where(Skill.id == skill_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if skill is None or skill.owner_id not in {None, actor_id}:
        raise ValueError("Skill unavailable")
    if skill.owner_id is None:
        own = await db.scalar(
            select(Skill.id).where(Skill.owner_id == actor_id, Skill.name == skill.name)
        )
        if not skill.admin_enabled or own is not None:
            raise ValueError("Skill unavailable")
    state = await db.scalar(
        select(UserSkillState)
        .where(UserSkillState.user_id == actor_id, UserSkillState.skill_id == skill_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if state is None:
        raise ValueError("Skill unavailable")
    return state


async def set_personal_state(
    db: AsyncSession, actor_id: UUID, skill_id: UUID, *, enabled: bool
) -> None:
    state = await personal_state(db, actor_id, skill_id)
    state.is_active = enabled
    await db.flush()
