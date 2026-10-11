"""Read the original personal gallery visibility and exact-scope cache metadata."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.skill_read_schemas import (
    SkillReadInput,
    SkillReadItem,
    SkillReadProjection,
)
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.skills.preference_service import SkillPreferenceService
from src.domains.skills.ui_projection import merge_skill_metadata


async def require_skill_access(db: AsyncSession, actor_id: UUID) -> None:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.SKILLS)
    await load_actor(db, actor_id)


async def read_skills(
    db: AsyncSession, actor_id: UUID, query: SkillReadInput
) -> SkillReadProjection:
    selected = SkillReadInput.model_validate(query.model_dump())
    await require_skill_access(db, actor_id)
    visible = await SkillPreferenceService(db).get_user_visible_skills(actor_id)
    page = visible[selected.offset : selected.offset + selected.limit]
    items = tuple(
        SkillReadItem.model_validate(merge_skill_metadata(row, enabled_for_user=row["is_active"]))
        for row in page
    )
    await require_skill_access(db, actor_id)
    next_offset = selected.offset + len(items)
    result = SkillReadProjection(
        observed_at=datetime.now(UTC),
        items=items,
        total=len(visible),
        next_offset=next_offset if next_offset < len(visible) else None,
    )
    if len(result.model_dump_json().encode("utf-8")) > 64_000:
        raise ValueError("Skill metadata projection too large; request a smaller page")
    return result


async def observe_visible_skill(db: AsyncSession, actor_id: UUID, skill_id: UUID) -> SkillReadItem:
    visible = await SkillPreferenceService(db).get_user_visible_skills(actor_id)
    row = next((row for row in visible if row["skill_id"] == str(skill_id)), None)
    if row is None:
        raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED")
    return SkillReadItem.model_validate(
        merge_skill_metadata(row, enabled_for_user=row["is_active"])
    )
