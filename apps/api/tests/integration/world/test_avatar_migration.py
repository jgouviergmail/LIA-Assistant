"""Real PostgreSQL round trip: nullable preferences preserve existing account data."""

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration


async def test_avatar_migration_round_trip_preserves_existing_users(
    async_engine: AsyncEngine,
) -> None:
    path = (
        Path(__file__).parents[3]
        / "alembic/versions/2026_10_25_1700-a85f7c4d2e19_world_avatar_preferences.py"
    )
    spec = importlib.util.spec_from_file_location("world_avatar_migration", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    schema = "avatar_migration_" + uuid4().hex
    async with async_engine.begin() as connection:
        await connection.execute(text(f"CREATE SCHEMA {schema}"))
        await connection.execute(text(f"SET LOCAL search_path TO {schema}"))
        await connection.execute(text("CREATE TABLE users (id int primary key, full_name text)"))
        await connection.execute(text("INSERT INTO users VALUES (1, 'Existing account')"))

        def exercise(sync: Connection) -> None:
            with Operations.context(MigrationContext.configure(sync)):
                migration.upgrade()
                assert (
                    sync.execute(text("SELECT world_avatar_preferences FROM users")).scalar_one()
                    is None
                )
                sync.execute(
                    text("UPDATE users SET world_avatar_preferences = cast(:prefs as jsonb)"),
                    {"prefs": '{"version":1}'},
                )
                migration.downgrade()
                assert (
                    sync.execute(text("SELECT full_name FROM users")).scalar_one()
                    == "Existing account"
                )
                migration.upgrade()
                assert (
                    sync.execute(text("SELECT world_avatar_preferences FROM users")).scalar_one()
                    is None
                )

        await connection.run_sync(exercise)
        await connection.execute(text("SET LOCAL search_path TO public"))
        await connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
