"""The settings routes of a skill's life (lot 14): its use, its previous version, the switch-off."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceNotFoundError
from src.domains.skills.import_service import SkillImportService
from src.domains.skills.lifecycle_router import (
    SkillDormantDecisionRequest,
    restore_previous_skill,
    settle_dormant_skills,
)
from src.domains.skills.models import Skill, UserSkillState
from src.domains.skills.router import list_skills
from src.domains.users.models import User
from tests.helpers.committed_account_session import async_session as async_session
from tests.integration.domains.skill_library.test_library_install import _user
from tests.integration.domains.skill_library.test_library_install import skill_dirs as skill_dirs
from tests.unit.domains.skill_library.fakes import manifest

pytestmark = pytest.mark.integration


async def _person_with(db: AsyncSession, *versions: tuple[str, str]) -> User:
    actor = await _user(db)
    for name, words in versions:
        await SkillImportService(db).import_upload(
            manifest(name, words), "SKILL.md", owner_id=actor, is_system=False
        )
    person = await db.get(User, actor)
    assert person is not None
    return person


async def test_the_listing_says_which_skills_can_go_back_to_their_previous_version(
    async_session: AsyncSession, skill_dirs: Path
) -> None:
    person = await _person_with(
        async_session, ("notes", "First words"), ("notes", "Second words"), ("drafts", "Only")
    )

    listing = await list_skills(person, async_session)

    items = {item["name"]: item for item in listing["skills"]}
    assert isinstance(items["notes"]["previous_version_at"], datetime)
    assert items["drafts"]["previous_version_at"] is None
    assert items["drafts"]["use_count"] == 0 and items["drafts"]["dormant"] is False
    assert listing["dormant_after_days"] == settings.skills_dormant_after_days


async def test_the_restore_route_answers_the_restored_skill(
    async_session: AsyncSession, skill_dirs: Path
) -> None:
    person = await _person_with(async_session, ("notes", "First words"), ("notes", "Second words"))

    restored = await restore_previous_skill("notes", person, async_session)

    assert (restored["name"], restored["description"]) == ("notes", "First words")
    assert restored["scope"] == "user"


async def test_the_restore_route_says_when_there_is_nothing_to_restore(
    async_session: AsyncSession, skill_dirs: Path
) -> None:
    person = await _person_with(async_session, ("notes", "First words"))

    with pytest.raises(ResourceNotFoundError):
        await restore_previous_skill("notes", person, async_session)


@pytest.mark.parametrize(
    ("decision", "active", "kept"), [("switch_off", False, False), ("keep", True, True)]
)
async def test_the_dormant_route_applies_the_answer_to_the_shown_skills(
    async_session: AsyncSession, skill_dirs: Path, decision: str, active: bool, kept: bool
) -> None:
    person = await _person_with(async_session, ("notes", "Words"))
    skill_id = await async_session.scalar(
        select(Skill.id).where(Skill.owner_id == person.id, Skill.name == "notes")
    )
    assert skill_id is not None
    long_ago = datetime.now(UTC) - timedelta(days=settings.skills_dormant_after_days + 1)
    await async_session.execute(
        update(UserSkillState)
        .where(UserSkillState.skill_id == skill_id)
        .values(usage_counted_since=long_ago)
    )
    await async_session.commit()

    answer = await settle_dormant_skills(
        SkillDormantDecisionRequest.model_validate({"skill_ids": [skill_id], "decision": decision}),
        person,
        async_session,
    )

    assert answer == {"decision": decision, "settled": ["notes"]}
    await async_session.rollback()  # the route committed: read what was written
    state = await async_session.scalar(
        select(UserSkillState).where(UserSkillState.skill_id == skill_id)
    )
    assert state is not None
    assert (state.is_active, state.dormancy_kept_at is not None) == (active, kept)
