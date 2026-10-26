"""Real SQL ownership, concurrent edits and independence from home/preferences."""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.users.models import User
from src.domains.world.avatar import AvatarAppearance, AvatarUpdate
from src.domains.world.avatar_service import read_owner_avatar, update_owner_avatar
from src.domains.world.home import HomeUpdate
from src.domains.world.home_service import update_owner_home

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "language,fallback",
    [
        ("en", "LIA explorer"),
        ("fr", "Explorateur LIA"),
        ("de", "LIA-Entdecker"),
        ("es", "Explorador LIA"),
        ("it", "Esploratore LIA"),
        ("zh-CN", "LIA 探索者"),
    ],
)
async def test_avatar_is_account_scoped_and_never_uses_email_as_a_name(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
    language: str,
    fallback: str,
) -> None:
    monkeypatch.setattr(settings, "world_enabled", True)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as db:
        first = User(
            email=f"avatar-{uuid4().hex}@example.invalid",
            full_name="Éloïse",
            is_active=True,
        )
        other = User(
            email=f"avatar-{uuid4().hex}@example.invalid",
            full_name=None,
            is_active=True,
            language=language,
        )
        db.add_all([first, other])
        await db.flush()
        committed_user_ids.extend([first.id, other.id])
        await db.commit()
    initial = await read_owner_avatar(first.id)
    assert initial.needs_setup and not initial.needs_reset
    assert initial.public_name == "Éloïse"
    saved = await update_owner_avatar(
        first.id,
        AvatarUpdate(
            expected_revision=0,
            appearance=AvatarAppearance(hair="bald", glasses=True),
            consent=True,
        ),
    )
    assert saved.preferences.revision == 1 and not saved.needs_setup
    assert saved.preferences.appearance.hair == "bald"
    second = await read_owner_avatar(other.id)
    assert second.needs_setup and second.public_name == fallback
    assert first.email not in saved.model_dump_json()
    assert second.preferences.appearance != saved.preferences.appearance


async def test_avatar_and_home_writes_preserve_each_other_and_enforce_cas(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "world_enabled", True)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as db:
        owner = User(email=f"avatar-{uuid4().hex}@example.invalid", is_active=True)
        db.add(owner)
        await db.flush()
        committed_user_ids.append(owner.id)
        await db.commit()
    await asyncio.gather(
        update_owner_avatar(
            owner.id,
            AvatarUpdate(
                expected_revision=0,
                appearance=AvatarAppearance(outfit="dress"),
                consent=True,
            ),
        ),
        update_owner_home(owner.id, HomeUpdate(expected_revision=0, palette="violet")),
    )
    results = await asyncio.gather(
        update_owner_avatar(
            owner.id,
            AvatarUpdate(
                expected_revision=1,
                appearance=AvatarAppearance(hair="long"),
                consent=True,
            ),
        ),
        update_owner_avatar(
            owner.id,
            AvatarUpdate(
                expected_revision=1,
                appearance=AvatarAppearance(hair="curly"),
                consent=True,
            ),
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(result, ResourceConflictError) for result in results) == 1
    view = await read_owner_avatar(owner.id)
    assert view.preferences.revision == 2
    async with factory() as db:
        stored = await db.get(User, owner.id)
        assert stored is not None and stored.world_preferences is not None
        assert stored.world_preferences["palette"] == "violet"
        assert stored.world_avatar_preferences is not None
        assert "violet" not in str(stored.world_avatar_preferences)


async def test_corrupted_avatar_requires_explicit_reset_and_inactive_owner_is_refused(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "world_enabled", True)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as db:
        owner = User(
            email=f"avatar-{uuid4().hex}@example.invalid",
            is_active=True,
            world_avatar_preferences={"private_memory": "SECRET"},
        )
        db.add(owner)
        await db.flush()
        committed_user_ids.append(owner.id)
        await db.commit()
    view = await read_owner_avatar(owner.id)
    assert view.needs_reset and "SECRET" not in view.model_dump_json()
    request = AvatarUpdate(expected_revision=0, appearance=AvatarAppearance(), consent=True)
    with pytest.raises(ResourceConflictError):
        await update_owner_avatar(owner.id, request)
    reset = await update_owner_avatar(owner.id, request.model_copy(update={"reset": True}))
    assert not reset.needs_reset
    async with factory() as db:
        stored = await db.get(User, owner.id)
        assert stored is not None
        stored.is_active = False
        await db.commit()
    with pytest.raises(AuthorizationError):
        await read_owner_avatar(owner.id)
    with pytest.raises(AuthorizationError):
        await update_owner_avatar(owner.id, request)
