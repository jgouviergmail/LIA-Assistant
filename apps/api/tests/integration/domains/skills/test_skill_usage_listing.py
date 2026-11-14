"""The settings listing carries how often each skill was used (lot 14), on PostgreSQL."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.skills.models import UserSkillState
from src.domains.skills.preference_service import SkillPreferenceService
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration

USED_AT = datetime(2026, 11, 2, 8, 30, tzinfo=UTC)


async def test_a_new_state_knows_when_counting_began_without_a_reload(
    async_session: AsyncSession,
) -> None:
    person = UserFactory.create()
    async_session.add(person)
    await async_session.flush()
    skill = await SkillPreferenceService(async_session).create_skill_for_import(
        name="fresh", description="fresh for tests", is_system=False, owner_id=person.id
    )
    other = UserFactory.create()
    async_session.add(other)
    await async_session.flush()
    state = UserSkillState(user_id=other.id, skill_id=skill.id, is_active=True)
    async_session.add(state)
    await async_session.flush()

    # Read straight off the flushed object, as a door reading a state it just
    # created does: an expired attribute would need a lazy load, which an async
    # session refuses. The model's own default guarantees it.
    assert state.usage_counted_since is not None


async def test_each_listed_skill_says_how_often_and_when_it_was_last_used(
    async_session: AsyncSession,
) -> None:
    person = UserFactory.create()
    async_session.add(person)
    await async_session.flush()
    service = SkillPreferenceService(async_session)
    used = await service.create_skill_for_import(
        name="notes", description="notes for tests", is_system=False, owner_id=person.id
    )
    await service.create_skill_for_import(
        name="drafts", description="drafts for tests", is_system=False, owner_id=person.id
    )
    # As the usage door writes it: one statement, the session's objects synchronised.
    await async_session.execute(
        update(UserSkillState)
        .where(UserSkillState.skill_id == used.id)
        .values(use_count=4, last_used_at=USED_AT)
    )
    await async_session.flush()

    items = {item["name"]: item for item in await service.get_user_visible_skills(person.id)}

    assert (items["notes"]["use_count"], items["notes"]["last_used_at"]) == (4, USED_AT)
    assert (items["drafts"]["use_count"], items["drafts"]["last_used_at"]) == (0, None)
    # When counting began for the state: its creation for a state created now.
    state = await async_session.scalar(
        select(UserSkillState).where(UserSkillState.skill_id == used.id)
    )
    assert state is not None and state.usage_counted_since is not None
    assert items["notes"]["counted_since"] == state.usage_counted_since
