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


@pytest.mark.parametrize(
    ("filename", "column"),
    [
        ("2026_10_25_1700-a85f7c4d2e19_world_avatar_preferences.py", "world_avatar_preferences"),
        (
            "2026_10_27_0259-e5f51d793219_add_private_world_experience_preferences.py",
            "world_experience_preferences",
        ),
    ],
)
async def test_world_preference_migration_round_trip_preserves_existing_users(
    async_engine: AsyncEngine,
    filename: str,
    column: str,
) -> None:
    path = Path(__file__).parents[3] / "alembic/versions" / filename
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
                assert sync.execute(text(f"SELECT {column} FROM users")).scalar_one() is None
                sync.execute(
                    text(f"UPDATE users SET {column} = cast(:prefs as jsonb)"),
                    {"prefs": '{"version":1}'},
                )
                migration.downgrade()
                assert (
                    sync.execute(text("SELECT full_name FROM users")).scalar_one()
                    == "Existing account"
                )
                migration.upgrade()
                assert sync.execute(text(f"SELECT {column} FROM users")).scalar_one() is None

        await connection.run_sync(exercise)
        await connection.execute(text("SET LOCAL search_path TO public"))
        await connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
