"""Owner persistence, source forgetting and races against real disposable SQL."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.interests.models import UserInterest
from src.domains.memories.models import Memory
from src.domains.users.models import User
from src.domains.world.home import HomeUpdate
from src.domains.world.home_service import read_owner_home, update_owner_home

pytestmark = pytest.mark.integration


async def test_home_colours_are_owner_scoped_without_learning_reads_or_writes(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "world_enabled", True)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as db:
        owners = [
            User(email=f"home-{uuid4().hex}@example.invalid", is_active=True) for _ in range(2)
        ]
        db.add_all(owners)
        await db.flush()
        committed_user_ids.extend(user.id for user in owners)
        memories = [
            Memory(user_id=user.id, content=text, category="preference", char_count=len(text))
            for user, text in zip(owners, ["I love books", "I love music"], strict=True)
        ]
        db.add_all(memories)
        await db.commit()
        memory_id = memories[0].id
    first = await read_owner_home(owners[0].id)
    second = await read_owner_home(owners[1].id)
    assert first.owner_id == str(owners[0].id)
    assert first.decoration.palette == second.decoration.palette
    assert owners[1].id.hex not in first.model_dump_json()
    saved = await update_owner_home(
        owners[0].id,
        HomeUpdate(
            expected_revision=0,
            palette="sage",
        ),
    )
    async with factory() as db:
        row = await db.get(Memory, memory_id)
        assert row is not None and row.usage_count == 0 and row.last_accessed_at is None
        row.invalidated_at = datetime.now(UTC)
        await db.commit()
    forgotten = await read_owner_home(owners[0].id)
    assert forgotten.decoration == saved.decoration
    assert forgotten.decoration.palette == "sage"
    async with factory() as db:
        row = await db.get(User, owners[0].id)
        assert row is not None
        stored = row.world_preferences
        assert (
            stored is not None and "I love" not in str(stored) and str(memory_id) not in str(stored)
        )
        untouched = await db.scalar(select(Memory).where(Memory.id == memory_id))
        assert (
            untouched is not None
            and untouched.usage_count == 0
            and untouched.last_accessed_at is None
        )


async def test_concurrent_home_edits_require_a_fresh_revision(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "world_enabled", True)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as db:
        owner = User(email=f"home-{uuid4().hex}@example.invalid", is_active=True)
        db.add(owner)
        await db.flush()
        committed_user_ids.append(owner.id)
        await db.commit()
    results = await asyncio.gather(
        update_owner_home(owner.id, HomeUpdate(expected_revision=0, palette="sage")),
        update_owner_home(owner.id, HomeUpdate(expected_revision=0, palette="teal")),
        return_exceptions=True,
    )
    assert sum(isinstance(result, ResourceConflictError) for result in results) == 1
    final = await read_owner_home(owner.id)
    assert final.preferences.revision == 1
    assert final.preferences.palette in {"sage", "teal"}


async def test_home_ignores_sources_regardless_of_learning_and_notification_preferences(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "world_enabled", True)
    monkeypatch.setattr(settings, "memory_extraction_enabled", False)
    monkeypatch.setattr(settings, "interest_extraction_enabled", False)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as db:
        owner = User(
            email=f"home-{uuid4().hex}@example.invalid", is_active=True, interests_enabled=False
        )
        db.add(owner)
        await db.flush()
        committed_user_ids.append(owner.id)
        db.add(
            Memory(user_id=owner.id, content="I love books", category="preference", char_count=12)
        )
        db.add(
            UserInterest(
                user_id=owner.id,
                topic="Fictional garden",
                category="nature",
                status="active",
                last_mentioned_at=datetime.now(UTC),
            )
        )
        db.add(
            UserInterest(
                user_id=owner.id,
                topic="Fictional blocked topic",
                category="science",
                status="blocked",
                last_mentioned_at=datetime.now(UTC),
            )
        )
        await db.commit()
    view = await read_owner_home(owner.id)
    assert view.preferences.revision == 0
    async with factory() as db:
        row = await db.get(User, owner.id)
        assert row is not None and not row.interests_enabled


async def test_home_saves_colours_and_refuses_deactivated_accounts(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "world_enabled", True)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with factory() as db:
        owner = User(
            email=f"home-{uuid4().hex}@example.invalid", is_active=True, memory_enabled=False
        )
        db.add(owner)
        await db.flush()
        committed_user_ids.append(owner.id)
        db.add(
            Memory(user_id=owner.id, content="I love books", category="preference", char_count=12)
        )
        db.add(
            UserInterest(
                user_id=owner.id,
                topic="Fictional garden",
                category="nature",
                status="active",
                last_mentioned_at=datetime.now(UTC),
            )
        )
        await db.commit()
    assert (await read_owner_home(owner.id)).preferences.revision == 0
    saved = await update_owner_home(
        owner.id,
        HomeUpdate(
            expected_revision=0,
        ),
    )
    assert saved.preferences.revision == 1
    async with factory() as db:
        row = await db.get(User, owner.id)
        assert row is not None
        row.is_active = False
        await db.commit()
    with pytest.raises(AuthorizationError):
        await read_owner_home(owner.id)
    with pytest.raises(AuthorizationError):
        await update_owner_home(owner.id, HomeUpdate(expected_revision=1, palette="sage"))


async def test_unreadable_home_requires_explicit_repair_without_learning_reads(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "world_enabled", True)
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    legacy = {"version": 999, "revision": 4, "palette": "teal"}
    async with factory() as db:
        owner = User(
            email=f"home-{uuid4().hex}@example.invalid", is_active=True, world_preferences=legacy
        )
        db.add(owner)
        await db.flush()
        committed_user_ids.append(owner.id)
        await db.commit()
    statements: list[str] = []

    def trace(
        _conn: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _many: bool,
    ) -> None:
        statements.append(statement.lower())

    event.listen(async_engine.sync_engine, "before_cursor_execute", trace)
    try:
        first = await read_owner_home(owner.id)
        assert first.needs_reset
        assert first.preferences.revision == 0
        async with factory() as db:
            row = await db.get(User, owner.id)
            assert row is not None and row.world_preferences == legacy
        saved = await update_owner_home(
            owner.id,
            HomeUpdate(
                expected_revision=0,
                reset=True,
            ),
        )
        assert saved.preferences.revision == 1
        assert statements
        assert not any(
            "from memories" in query
            or "from user_interests" in query
            or "join memories" in query
            or "join user_interests" in query
            for query in statements
        )
    finally:
        event.remove(async_engine.sync_engine, "before_cursor_execute", trace)
