"""Per-account skill names against REAL PostgreSQL (ADR-327, lot 0).

The uniqueness moved from ``name`` to (scope, name): system names stay unique
among system skills, a person's names are unique among their own. Those rules
live in two partial unique indexes and one CHECK, which only a real database
executes — a mocked repository would accept anything. Every statement below
runs for real (``async_session``: outer transaction + SAVEPOINT, nothing
persists).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.skills.models import Skill, UserSkillState
from src.domains.skills.preference_service import SkillPreferenceService
from src.domains.skills.repository import SkillRepository, UserSkillStateRepository
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration


async def _user(db: AsyncSession) -> uuid.UUID:
    user = UserFactory.create()
    db.add(user)
    await db.flush()
    return user.id


async def _skill(db: AsyncSession, name: str, owner: uuid.UUID | None) -> Skill:
    svc = SkillPreferenceService(db)
    return await svc.create_skill_for_import(
        name=name,
        description=f"{name} for tests",
        is_system=owner is None,
        owner_id=owner,
    )


class TestUniquenessIsPerScope:
    @pytest.mark.asyncio
    async def test_two_people_may_keep_the_same_name(self, async_session: AsyncSession) -> None:
        alice, bob = await _user(async_session), await _user(async_session)
        first = await _skill(async_session, "pdf", alice)
        second = await _skill(async_session, "pdf", bob)
        assert first.id != second.id
        assert {first.owner_id, second.owner_id} == {alice, bob}

    @pytest.mark.asyncio
    async def test_a_person_cannot_hold_a_name_twice(self, async_session: AsyncSession) -> None:
        alice = await _user(async_session)
        async_session.add(Skill(name="pdf", is_system=False, owner_id=alice, description="a"))
        await async_session.flush()
        async_session.add(Skill(name="pdf", is_system=False, owner_id=alice, description="b"))
        with pytest.raises(IntegrityError):
            await async_session.flush()

    @pytest.mark.asyncio
    async def test_system_names_stay_unique(self, async_session: AsyncSession) -> None:
        system = {"is_system": True, "owner_id": None, "provenance": "system"}
        async_session.add(Skill(name="brief", description="a", **system))
        await async_session.flush()
        async_session.add(Skill(name="brief", description="b", **system))
        with pytest.raises(IntegrityError):
            await async_session.flush()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("is_system", [True, False])
    async def test_system_means_no_owner(
        self, async_session: AsyncSession, is_system: bool
    ) -> None:
        """A system skill with an owner, or a user skill without one, is refused."""
        owner = await _user(async_session) if is_system else None
        async_session.add(Skill(name="odd", is_system=is_system, owner_id=owner, description="x"))
        with pytest.raises(IntegrityError):
            await async_session.flush()

    @pytest.mark.asyncio
    async def test_a_person_may_shadow_a_system_name(self, async_session: AsyncSession) -> None:
        """The database allows it; the IMPORT refuses it (S2) — an admin import may create it."""
        alice = await _user(async_session)
        await _skill(async_session, "brief", alice)
        await _skill(async_session, "brief", None)  # admin import after the person's
        rows = (await async_session.execute(select(Skill).where(Skill.name == "brief"))).scalars()
        assert sorted(str(r.owner_id) for r in rows) == sorted([str(alice), "None"])


class TestLookupsNameTheirScope:
    @pytest.mark.asyncio
    async def test_resolution_prefers_the_person_s_own(self, async_session: AsyncSession) -> None:
        alice, bob = await _user(async_session), await _user(async_session)
        system = await _skill(async_session, "brief", None)
        own = await _skill(async_session, "brief", alice)
        repo = SkillRepository(async_session)
        assert (await repo.resolve_for_user(alice, "brief")).id == own.id
        assert (await repo.resolve_for_user(bob, "brief")).id == system.id
        assert (await repo.get_system("brief")).id == system.id
        assert (await repo.get_owned(alice, "brief")).id == own.id
        assert await repo.get_owned(bob, "brief") is None

    @pytest.mark.asyncio
    async def test_nobody_resolves_someone_else_s_skill(self, async_session: AsyncSession) -> None:
        alice, bob = await _user(async_session), await _user(async_session)
        await _skill(async_session, "pdf", alice)
        assert await SkillRepository(async_session).resolve_for_user(bob, "pdf") is None


class TestPreferencesActOnOneAccount:
    @pytest.mark.asyncio
    async def test_delete_removes_that_row_only(self, async_session: AsyncSession) -> None:
        alice, bob = await _user(async_session), await _user(async_session)
        mine = await _skill(async_session, "pdf", alice)
        theirs = await _skill(async_session, "pdf", bob)
        await SkillPreferenceService(async_session).delete_skill(mine.id)
        await async_session.flush()
        left = (await async_session.execute(select(Skill.id).where(Skill.name == "pdf"))).all()
        assert [row[0] for row in left] == [theirs.id]
        states = await async_session.execute(
            select(UserSkillState).where(UserSkillState.skill_id == mine.id)
        )
        assert states.first() is None

    @pytest.mark.asyncio
    async def test_toggle_flips_the_person_s_own_state(self, async_session: AsyncSession) -> None:
        alice, bob = await _user(async_session), await _user(async_session)
        await _skill(async_session, "pdf", alice)
        await _skill(async_session, "pdf", bob)
        await async_session.flush()
        svc = SkillPreferenceService(async_session)
        assert await svc.toggle_user_skill(alice, "pdf") is False
        states = UserSkillStateRepository(async_session)
        assert "pdf" not in await states.get_active_skill_names(alice)
        assert "pdf" in await states.get_active_skill_names(bob)

    @pytest.mark.asyncio
    async def test_a_disabled_own_skill_is_not_revived_by_the_system_one(
        self, async_session: AsyncSession
    ) -> None:
        """The active set is a set of NAMES: it must read the skill the name resolves to."""
        alice = await _user(async_session)
        await _skill(async_session, "brief", None)
        await SkillPreferenceService(async_session).ensure_user_skills(alice)
        await _skill(async_session, "brief", alice)
        await async_session.flush()
        states = UserSkillStateRepository(async_session)
        assert "brief" in await states.get_active_skill_names(alice)
        await SkillPreferenceService(async_session).toggle_user_skill(alice, "brief")
        await async_session.flush()
        assert "brief" not in await states.get_active_skill_names(alice)

    @pytest.mark.asyncio
    async def test_listing_shows_the_skill_that_resolves(self, async_session: AsyncSession) -> None:
        alice = await _user(async_session)
        await _skill(async_session, "brief", None)
        await _skill(async_session, "other", None)
        await SkillPreferenceService(async_session).ensure_user_skills(alice)
        await _skill(async_session, "brief", alice)
        await async_session.flush()
        items = await SkillPreferenceService(async_session).get_user_visible_skills(alice)
        by_name = {item["name"]: item["scope"] for item in items}
        assert by_name == {"brief": "user", "other": "admin"}
        assert len(items) == 2


class TestDiskSyncKeysOnIdentity:
    @pytest.mark.asyncio
    async def test_same_name_in_two_accounts_is_two_identities(
        self, async_session: AsyncSession
    ) -> None:
        alice, bob = await _user(async_session), await _user(async_session)
        await _skill(async_session, "stale", alice)
        await async_session.flush()
        entries: list[dict[str, Any]] = [
            {"name": "pdf", "scope": "user", "owner_id": str(alice), "description": "a"},
            {"name": "pdf", "scope": "user", "owner_id": str(bob), "description": "b"},
        ]
        cache = type("Cache", (), {})()
        cache.get_all = lambda: entries  # type: ignore[attr-defined]

        from unittest.mock import patch

        with patch("src.domains.skills.cache.SkillsCache", cache):
            result = await SkillPreferenceService(async_session).sync_from_disk()

        assert sorted(result.created) == ["pdf", "pdf"]
        assert result.removed == ["stale"]
        owners = (
            await async_session.execute(select(Skill.owner_id).where(Skill.name == "pdf"))
        ).all()
        assert sorted(str(row[0]) for row in owners) == sorted([str(alice), str(bob)])
        # A person's recovered skill is visible to that person, not registered blind.
        await async_session.flush()
        states = UserSkillStateRepository(async_session)
        assert "pdf" in await states.get_active_skill_names(alice)
        assert "pdf" in await states.get_active_skill_names(bob)

    @pytest.mark.asyncio
    async def test_a_folder_whose_owner_is_gone_is_left_alone(
        self, async_session: AsyncSession
    ) -> None:
        """Its row would violate the owner FK and abort the whole sync."""
        alice = await _user(async_session)
        entries: list[dict[str, Any]] = [
            {"name": "kept", "scope": "user", "owner_id": str(alice), "description": "a"},
            {"name": "orphan", "scope": "user", "owner_id": str(uuid.uuid4()), "description": "o"},
            {"name": "junk", "scope": "user", "owner_id": "not-an-id", "description": "j"},
        ]
        cache = type("Cache", (), {})()
        cache.get_all = lambda: entries  # type: ignore[attr-defined]

        from unittest.mock import patch

        with patch("src.domains.skills.cache.SkillsCache", cache):
            result = await SkillPreferenceService(async_session).sync_from_disk()

        assert result.created == ["kept"]
