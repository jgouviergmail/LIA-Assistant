"""Run the catalogue revision's actual migration both ways on disposable PostgreSQL."""

import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.infrastructure.database.owner_lock import INSTANCE_OWNER

pytestmark = pytest.mark.integration

PATH = (
    Path(__file__).resolve().parents[4]
    / "alembic/versions/2026_10_15_0030-7f428c3e0a19_fishaudio_catalogue_revision.py"
)


async def test_migration_creates_a_singleton_revision_and_rolls_back_cleanly(
    async_session: AsyncSession,
) -> None:
    spec = importlib.util.spec_from_file_location("fish_catalogue_revision_migration", PATH)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    async def run(step: str) -> None:
        operation = cast(Callable[[], None], getattr(migration, step))

        def apply(sync_session: Session) -> None:
            with Operations.context(MigrationContext.configure(sync_session.connection())):
                operation()

        await async_session.run_sync(apply)

    # The fixture owns a rolled-back test transaction: no development database
    # or other test's committed schema is altered by this migration replay.
    await async_session.execute(text("DROP TABLE fishaudio_catalogue_revisions"))
    await run("upgrade")
    generation = uuid4()
    await async_session.execute(
        text(
            "INSERT INTO fishaudio_catalogue_revisions (id, generation) VALUES (:id, :generation)"
        ),
        {"id": INSTANCE_OWNER, "generation": generation},
    )
    assert (
        await async_session.scalar(text("SELECT generation FROM fishaudio_catalogue_revisions"))
        == generation
    )
    assert await async_session.scalar(
        text(
            "SELECT created_at IS NOT NULL AND updated_at IS NOT NULL FROM fishaudio_catalogue_revisions"
        )
    )
    assert (
        await async_session.scalar(
            text("SELECT pending_removals FROM fishaudio_catalogue_revisions")
        )
        == {}
    )
    with pytest.raises(IntegrityError):
        async with async_session.begin_nested():
            await async_session.execute(
                text("UPDATE fishaudio_catalogue_revisions SET pending_removals = '[]'::jsonb")
            )
    with pytest.raises(IntegrityError):
        async with async_session.begin_nested():
            await async_session.execute(
                text(
                    "INSERT INTO fishaudio_catalogue_revisions (id, generation) VALUES (:id, :generation)"
                ),
                {"id": uuid4(), "generation": uuid4()},
            )
    await run("downgrade")
    assert (
        await async_session.scalar(text("SELECT to_regclass('fishaudio_catalogue_revisions')"))
        is None
    )
    await run("upgrade")
    assert (
        await async_session.scalar(text("SELECT count(*) FROM fishaudio_catalogue_revisions")) == 0
    )
