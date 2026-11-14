"""How often a person used a skill: one atomic count per run, on their own state (lot 14).

On PostgreSQL: the count is ONE ``UPDATE`` with column arithmetic, idempotent per
run, so two concurrent runs both count and a run that activates its skill twice
counts once. The name resolves as the turn resolves it: the person's own skill
before a system skill of the same name, never another person's.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.domains.skills.models import Skill, UserSkillState
from src.domains.skills.usage import record_skill_use
from tests.helpers.committed_users import commit_owner

pytestmark = pytest.mark.integration


@dataclass
class Rows:
    """Sessions on the test database, and the system skills a test created."""

    sessions: async_sessionmaker[AsyncSession]
    system_skills: list[UUID] = field(default_factory=list)

    async def skill(self, name: str, owner: UUID | None = None) -> UUID:
        async with self.sessions() as db:
            row = Skill(
                name=name,
                is_system=owner is None,
                owner_id=owner,
                description=f"{name} for tests",
                provenance="system" if owner is None else "authored",
            )
            db.add(row)
            await db.commit()
            if owner is None:
                self.system_skills.append(row.id)
            return row.id

    async def state(self, user: UUID, skill: UUID) -> None:
        async with self.sessions() as db:
            db.add(UserSkillState(user_id=user, skill_id=skill, is_active=True))
            await db.commit()

    async def count(self, user: UUID, skill: UUID) -> int:
        async with self.sessions() as db:
            state = await db.scalar(
                select(UserSkillState).where(
                    UserSkillState.user_id == user, UserSkillState.skill_id == skill
                )
            )
            assert state is not None
            if state.use_count:
                assert state.last_used_at is not None
            return state.use_count


@pytest_asyncio.fixture
async def rows(async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Rows]:
    """The door's own sessions, on the test database; system rows removed after."""
    created = Rows(async_sessionmaker(async_engine, expire_on_commit=False))

    @asynccontextmanager
    async def database() -> AsyncIterator[AsyncSession]:
        async with created.sessions() as db:
            yield db
            await db.commit()

    monkeypatch.setattr("src.domains.skills.usage.get_db_context", database)
    try:
        yield created
    finally:
        if created.system_skills:
            async with created.sessions() as db:
                await db.execute(delete(Skill).where(Skill.id.in_(created.system_skills)))
                await db.commit()


def _name() -> str:
    return f"usage-{uuid4().hex[:8]}"


async def test_a_use_is_counted_on_the_person_s_own_state(
    async_engine: AsyncEngine, committed_user_ids: list[UUID], rows: Rows
) -> None:
    user = await commit_owner(async_engine, committed_user_ids)
    name = _name()
    skill = await rows.skill(name)
    await rows.state(user, skill)

    await record_skill_use(user, name, run_id="run-1")

    assert await rows.count(user, skill) == 1


async def test_one_run_counts_once_however_often_it_activates(
    async_engine: AsyncEngine, committed_user_ids: list[UUID], rows: Rows
) -> None:
    user = await commit_owner(async_engine, committed_user_ids)
    name = _name()
    skill = await rows.skill(name)
    await rows.state(user, skill)

    await record_skill_use(user, name, run_id="run-1")
    await record_skill_use(user, name, run_id="run-1")
    await record_skill_use(user, name, run_id="run-2")

    assert await rows.count(user, skill) == 2


async def test_the_person_s_own_skill_is_counted_over_a_system_namesake(
    async_engine: AsyncEngine, committed_user_ids: list[UUID], rows: Rows
) -> None:
    user = await commit_owner(async_engine, committed_user_ids)
    name = _name()
    system = await rows.skill(name)
    own = await rows.skill(name, owner=user)
    await rows.state(user, system)
    await rows.state(user, own)

    await record_skill_use(user, name, run_id="run-1")

    assert (await rows.count(user, own), await rows.count(user, system)) == (1, 0)


async def test_another_account_is_never_counted(
    async_engine: AsyncEngine, committed_user_ids: list[UUID], rows: Rows
) -> None:
    user = await commit_owner(async_engine, committed_user_ids)
    other = await commit_owner(async_engine, committed_user_ids)
    name = _name()
    theirs = await rows.skill(name, owner=other)
    await rows.state(other, theirs)

    await record_skill_use(user, name, run_id="run-1")

    assert await rows.count(other, theirs) == 0


async def test_a_name_nobody_holds_counts_nothing(
    async_engine: AsyncEngine, committed_user_ids: list[UUID], rows: Rows
) -> None:
    user = await commit_owner(async_engine, committed_user_ids)

    await record_skill_use(user, f"absent-{uuid4().hex[:8]}", run_id="run-1")


async def test_concurrent_runs_are_all_counted(
    async_engine: AsyncEngine, committed_user_ids: list[UUID], rows: Rows
) -> None:
    user = await commit_owner(async_engine, committed_user_ids)
    name = _name()
    skill = await rows.skill(name)
    await rows.state(user, skill)

    await asyncio.gather(*(record_skill_use(user, name, run_id=f"run-{i}") for i in range(5)))

    assert await rows.count(user, skill) == 5
