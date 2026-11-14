"""The person's answer to the dormant-skills proposal (lot 14), on PostgreSQL.

Switch them off, or keep them: one door, the verdict taken again on the locked
state, and only for the skills the proposal showed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.skills.models import Skill, UserSkillState
from src.domains.skills.preference_service import SkillPreferenceService
from src.domains.skills.usage import DormantDecision, settle_dormant
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
DAYS = 60
LONG_AGO = NOW - timedelta(days=DAYS + 40)
OFF, KEEP = DormantDecision.SWITCH_OFF, DormantDecision.KEEP


async def _person_with(db: AsyncSession, *names: str) -> tuple[UUID, dict[str, Skill]]:
    person = UserFactory.create()
    db.add(person)
    await db.flush()
    service = SkillPreferenceService(db)
    skills = {}
    for name in names:
        skills[name] = await service.create_skill_for_import(
            name=name, description=f"{name} for tests", is_system=False, owner_id=person.id
        )
    await db.execute(
        update(UserSkillState)
        .where(UserSkillState.user_id == person.id)
        .values(usage_counted_since=LONG_AGO)
    )
    await db.flush()
    return person.id, skills


async def _states(db: AsyncSession, person: UUID) -> dict[UUID, UserSkillState]:
    rows = await db.scalars(select(UserSkillState).where(UserSkillState.user_id == person))
    return {row.skill_id: row for row in rows}


async def test_only_the_shown_skills_still_dormant_are_switched_off(
    async_session: AsyncSession,
) -> None:
    person, skills = await _person_with(async_session, "recent", "idle", "unshown")
    # Used yesterday: no longer dormant whatever the screen showed.
    await async_session.execute(
        update(UserSkillState)
        .where(UserSkillState.skill_id == skills["recent"].id)
        .values(use_count=1, last_used_at=NOW - timedelta(days=1))
    )
    await async_session.flush()
    shown = [skills["recent"].id, skills["idle"].id, skills["idle"].id]

    switched = await settle_dormant(
        async_session, person, shown, decision=OFF, now=NOW, after_days=DAYS
    )

    assert switched == ["idle"]
    states = await _states(async_session, person)
    assert states[skills["idle"].id].is_active is False
    assert states[skills["recent"].id].is_active is True
    # Dormant too, but never shown: the person did not decide about it.
    assert states[skills["unshown"].id].is_active is True
    # Asked again, nothing is left to switch off.
    again = await settle_dormant(
        async_session, person, shown, decision=OFF, now=NOW, after_days=DAYS
    )
    assert again == []


async def test_kept_skills_stay_on_and_are_not_proposed_again_for_a_whole_period(
    async_session: AsyncSession,
) -> None:
    person, skills = await _person_with(async_session, "idle")
    shown = [skills["idle"].id]

    kept = await settle_dormant(
        async_session, person, shown, decision=KEEP, now=NOW, after_days=DAYS
    )

    assert kept == ["idle"]
    state = (await _states(async_session, person))[skills["idle"].id]
    assert (state.is_active, state.dormancy_kept_at) == (True, NOW)
    # Kept: no longer dormant now, so a second answer settles nothing...
    assert (
        await settle_dormant(async_session, person, shown, decision=OFF, now=NOW, after_days=DAYS)
        == []
    )
    # ...until a whole period went by unused again.
    later = NOW + timedelta(days=DAYS + 1)
    assert await settle_dormant(
        async_session, person, shown, decision=OFF, now=later, after_days=DAYS
    ) == ["idle"]


async def test_a_skill_deleted_meanwhile_is_skipped_and_the_others_are_settled(
    async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.domains.skills import personal_state as module

    person, skills = await _person_with(async_session, "gone", "idle")
    real = module.personal_state

    async def deleted_between_read_and_lock(
        db: AsyncSession, actor_id: UUID, skill_id: UUID
    ) -> UserSkillState:
        if skill_id == skills["gone"].id:
            await db.execute(delete(Skill).where(Skill.id == skill_id))
        return await real(db, actor_id, skill_id)

    monkeypatch.setattr("src.domains.skills.usage.personal_state", deleted_between_read_and_lock)

    settled = await settle_dormant(
        async_session,
        person,
        [skills["gone"].id, skills["idle"].id],
        decision=OFF,
        now=NOW,
        after_days=DAYS,
    )

    assert settled == ["idle"]


async def test_locks_are_taken_in_one_order_whatever_the_order_asked(
    async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two answers naming the same skills in another order never wait on each other."""
    from src.domains.skills import personal_state as module

    person, skills = await _person_with(async_session, "alpha", "beta", "gamma")
    real, locked = module.personal_state, []

    async def recording(db: AsyncSession, actor_id: UUID, skill_id: UUID) -> UserSkillState:
        locked.append(skill_id)
        return await real(db, actor_id, skill_id)

    monkeypatch.setattr("src.domains.skills.usage.personal_state", recording)
    # Asked against the canonical order, so asking order and lock order differ.
    asked = sorted((skill.id for skill in skills.values()), key=str, reverse=True)
    name_of = {skill.id: name for name, skill in skills.items()}

    settled = await settle_dormant(
        async_session, person, asked, decision=KEEP, now=NOW, after_days=DAYS
    )

    assert locked == sorted(asked, key=str)
    # The answer still reads in the order asked.
    assert settled == [name_of[skill_id] for skill_id in asked]


async def test_a_skill_of_another_account_is_never_settled(
    async_session: AsyncSession,
) -> None:
    person, _ = await _person_with(async_session)
    other, theirs = await _person_with(async_session, "theirs")

    for decision in (OFF, KEEP):
        assert (
            await settle_dormant(
                async_session,
                person,
                [theirs["theirs"].id],
                decision=decision,
                now=NOW,
                after_days=DAYS,
            )
            == []
        )
    state = (await _states(async_session, other))[theirs["theirs"].id]
    assert (state.is_active, state.dormancy_kept_at) == (True, None)
