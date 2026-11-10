"""Prove display preference storage and migration contracts on PostgreSQL."""

import asyncio
import importlib.util
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.constants import USER_THEME_DARK_START_MINUTE, USER_THEME_LIGHT_START_MINUTE
from src.core.exceptions import ValidationError
from src.domains.users.models import User
from src.domains.users.schemas import UserProfile, UserUpdate
from src.domains.users.service import UserService

pytestmark = pytest.mark.integration


async def test_concurrent_partial_schedules_cannot_overwrite_the_other_boundary(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
) -> None:
    """Two sessions serialize validation; exactly one conflicting change succeeds."""
    owner_id = uuid4()
    committed_user_ids.append(owner_id)
    async with AsyncSession(async_engine) as seed:
        seed.add(User(id=owner_id, email=f"theme-{owner_id}@example.com", is_active=True))
        await seed.commit()

    async def change(data: UserUpdate) -> UserProfile:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            return await UserService(db).update_user(owner_id, data)

    results = await asyncio.gather(
        change(UserUpdate(theme_light_start_minute=600)),
        change(UserUpdate(theme_dark_start_minute=600)),
        return_exceptions=True,
    )
    assert sum(isinstance(result, UserProfile) for result in results) == 1
    assert sum(isinstance(result, ValidationError) for result in results) == 1
    async with AsyncSession(async_engine) as db:
        owner = await db.get(User, owner_id)
        assert owner is not None
        assert owner.theme_light_start_minute != owner.theme_dark_start_minute


async def test_schedule_profile_roundtrip_and_partial_merge(
    async_session: AsyncSession, test_user: User
) -> None:
    """The public write returns the schedule and validates a partial patch against it."""
    service = UserService(async_session)
    profile = await service.update_user(
        test_user.id,
        UserUpdate(
            theme="auto",
            theme_light_start_minute=1200,
            theme_dark_start_minute=420,
        ),
    )
    assert (profile.theme, profile.theme_light_start_minute, profile.theme_dark_start_minute) == (
        "auto",
        1200,
        420,
    )
    with pytest.raises(ValidationError):
        await service.update_user(test_user.id, UserUpdate(theme_dark_start_minute=1200))
    await async_session.refresh(test_user)
    assert test_user.theme_dark_start_minute == 420


@pytest.mark.parametrize(
    "assignment",
    [
        "theme_light_start_minute = -1",
        "theme_dark_start_minute = 1440",
        "theme_light_start_minute = theme_dark_start_minute",
    ],
)
async def test_database_refuses_invalid_schedule(
    async_session: AsyncSession, test_user: User, assignment: str
) -> None:
    """Scripts bypassing Pydantic still cannot persist an invalid interval."""
    async with async_session.begin_nested():
        with pytest.raises(IntegrityError):
            async with async_session.begin_nested():
                await async_session.execute(
                    text(f"UPDATE users SET {assignment} WHERE id = :id"), {"id": test_user.id}
                )


async def test_schedule_migration_roundtrip(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Downgrade removes only the feature; upgrade preserves manual choices."""
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic/versions/2026_11_09_0200-b74d02e6a193_user_theme_schedule.py"
    )
    spec = importlib.util.spec_from_file_location("theme_schedule_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def qualify(connection: Connection) -> None:
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(connection)))
        connection.execute(
            text("UPDATE users SET theme = 'oled' WHERE id = :id"), {"id": test_user.id}
        )
        migration.downgrade()
        assert "theme_light_start_minute" not in {
            column["name"] for column in inspect(connection).get_columns("users")
        }
        migration.upgrade()
        row = connection.execute(
            text(
                "SELECT theme, theme_light_start_minute, theme_dark_start_minute FROM users WHERE id = :id"
            ),
            {"id": test_user.id},
        ).one()
        assert tuple(row) == ("oled", USER_THEME_LIGHT_START_MINUTE, USER_THEME_DARK_START_MINUTE)
        connection.execute(
            text("UPDATE users SET theme = 'auto' WHERE id = :id"), {"id": test_user.id}
        )
        migration.downgrade()
        assert (
            connection.scalar(text("SELECT theme FROM users WHERE id = :id"), {"id": test_user.id})
            == "system"
        )
        migration.upgrade()

    await (await async_session.connection()).run_sync(qualify)
