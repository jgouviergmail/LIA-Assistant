"""Experience revisions, owner isolation and repair against disposable PostgreSQL."""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.account_export.builder import _fetch_user_profile
from src.domains.users.models import User
from src.domains.world.experience import ExperienceUpdate
from src.domains.world.experience_service import read_owner_experience, update_owner_experience
from src.domains.world.home import HomeUpdate
from src.domains.world.home_service import update_owner_home

pytestmark = pytest.mark.integration


async def test_experience_concurrent_write_has_one_winner(
    async_engine: AsyncEngine, committed_user_ids: list[UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "world_enabled", True)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as db:
        owner = User(email=f"experience-{uuid4().hex}@example.invalid", is_active=True)
        db.add(owner)
        await db.flush()
        committed_user_ids.append(owner.id)
        await db.commit()
    initial = await read_owner_experience(owner.id)
    assert initial.preferences.show_route and initial.preferences.revision == 0
    async with factory() as db:
        row = await db.get(User, owner.id)
        assert row is not None and row.world_experience_preferences is None
    results = await asyncio.gather(
        update_owner_experience(owner.id, ExperienceUpdate(expected_revision=0, show_route=False)),
        update_owner_experience(
            owner.id, ExperienceUpdate(expected_revision=0, hemisphere="south")
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(result, ResourceConflictError) for result in results) == 1
    final = await read_owner_experience(owner.id)
    assert final.preferences.revision == 1
    await update_owner_experience(
        owner.id, ExperienceUpdate(expected_revision=1, season_mode="off")
    )
    partial = await read_owner_experience(owner.id)
    assert partial.preferences.show_route == final.preferences.show_route
    assert partial.preferences.hemisphere == final.preferences.hemisphere
    assert partial.preferences.season_mode == "off"
    async with factory() as db:
        row = await db.get(User, owner.id)
        assert row is not None
        stored = row.world_experience_preferences
        assert isinstance(stored, dict)
        assert set(stored) == {"version", "revision", "show_route", "season_mode", "hemisphere"}
    await update_owner_home(owner.id, HomeUpdate(expected_revision=0, palette="teal"))
    assert (await read_owner_experience(owner.id)) == partial
    exported = await _fetch_user_profile(owner.id)
    assert exported["world_experience_preferences"] == partial.preferences.model_dump(mode="json")
    assert exported["world_preferences"]["palette"] == "teal"


async def test_experience_preserves_corruption_until_explicit_repair_and_refuses_inactive_owner(
    async_engine: AsyncEngine, committed_user_ids: list[UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "world_enabled", True)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    raw: dict[str, object] = {"version": 999, "show_route": False, "revision": 7}
    async with factory() as db:
        owners = [
            User(email=f"experience-{uuid4().hex}@example.invalid", is_active=True)
            for _ in range(2)
        ]
        owners[0].world_experience_preferences = raw
        db.add_all(owners)
        await db.flush()
        committed_user_ids.extend(owner.id for owner in owners)
        await db.commit()
    view = await read_owner_experience(owners[0].id)
    assert view.needs_reset and view.preferences.revision == 0
    assert (await read_owner_experience(owners[1].id)).owner_id == str(owners[1].id)
    async with factory() as db:
        row = await db.get(User, owners[0].id)
        assert row is not None and row.world_experience_preferences == raw
    with pytest.raises(ResourceConflictError):
        await update_owner_experience(
            owners[0].id, ExperienceUpdate(expected_revision=0, show_route=False)
        )
    repaired = await update_owner_experience(
        owners[0].id, ExperienceUpdate(expected_revision=0, reset=True)
    )
    assert not repaired.needs_reset and repaired.preferences.revision == 1
    assert repaired.preferences.show_route is True
    async with factory() as db:
        row = await db.get(User, owners[0].id)
        assert row is not None
        row.is_active = False
        await db.commit()
    with pytest.raises(AuthorizationError):
        await read_owner_experience(owners[0].id)
    with pytest.raises(AuthorizationError):
        await update_owner_experience(owners[0].id, ExperienceUpdate(expected_revision=1))


async def test_a_document_carrying_the_retired_introduction_needs_the_explicit_repair(
    async_engine: AsyncEngine, committed_user_ids: list[UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "world_enabled", True)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    retired: dict[str, object] = {
        "version": 1,
        "revision": 5,
        "show_route": False,
        "tutorial_version": 1,
        "tutorial_status": "completed",
        "season_mode": "winter",
        "hemisphere": "south",
    }
    async with factory() as db:
        owner = User(email=f"experience-{uuid4().hex}@example.invalid", is_active=True)
        owner.world_experience_preferences = retired
        db.add(owner)
        await db.flush()
        committed_user_ids.append(owner.id)
        await db.commit()
    view = await read_owner_experience(owner.id)
    assert view.needs_reset and view.preferences.revision == 0
    with pytest.raises(ResourceConflictError):
        await update_owner_experience(
            owner.id, ExperienceUpdate(expected_revision=0, season_mode="off")
        )
    async with factory() as db:
        row = await db.get(User, owner.id)
        assert row is not None and row.world_experience_preferences == retired
    repaired = await update_owner_experience(
        owner.id, ExperienceUpdate(expected_revision=0, reset=True)
    )
    assert not repaired.needs_reset and repaired.preferences.revision == 1
    async with factory() as db:
        row = await db.get(User, owner.id)
        assert row is not None
        assert row.world_experience_preferences == {
            "version": 1,
            "revision": 1,
            "show_route": True,
            "season_mode": "calendar",
            "hemisphere": "north",
        }
