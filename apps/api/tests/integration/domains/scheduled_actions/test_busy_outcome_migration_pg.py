"""A routine's busy outcome is enforced by PostgreSQL without rewriting its history."""

import importlib.util
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration
_VERSIONS = Path(__file__).resolve().parents[4] / "alembic/versions"


def _load(filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(filename, _VERSIONS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_busy_history_survives_upgrade_and_refuses_a_lossy_downgrade(
    async_engine: AsyncEngine,
) -> None:
    parent = _load("2026_09_05_0200-d8e9f0a1b2c3_scheduled_action_runs.py")
    change = _load("2026_11_10_1300-e70f2a4b6c83_scheduled_run_busy_outcome.py")
    owner, action = uuid4(), uuid4()

    def insert(connection: Connection, outcome: str) -> None:
        connection.execute(
            text(
                "INSERT INTO scheduled_action_runs "
                "(id,scheduled_action_id,user_id,started_at,ended_at,outcome,attempts,manual) "
                "VALUES (:id,:action,:owner,now(),now(),:outcome,0,false)"
            ),
            {"id": uuid4(), "action": action, "owner": owner, "outcome": outcome},
        )

    def check(connection: Connection) -> None:
        schema = f"routine_outcomes_{uuid4().hex}"
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        connection.execute(text("CREATE TABLE users (id uuid PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE scheduled_actions (id uuid PRIMARY KEY)"))
        connection.execute(text("INSERT INTO users VALUES (:id)"), {"id": owner})
        connection.execute(text("INSERT INTO scheduled_actions VALUES (:id)"), {"id": action})
        with Operations.context(MigrationContext.configure(connection)):
            parent.upgrade()
            for outcome in ("success", "failure", "skipped_condition", "proposed", "skipped_hitl"):
                insert(connection, outcome)
            original = connection.execute(
                text("SELECT * FROM scheduled_action_runs ORDER BY id")
            ).all()
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    insert(connection, "skipped_busy")
            change.upgrade()
            assert (
                connection.execute(text("SELECT * FROM scheduled_action_runs ORDER BY id")).all()
                == original
            )
            change.downgrade()
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    insert(connection, "skipped_busy")
            change.upgrade()
            insert(connection, "skipped_busy")
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    insert(connection, "not_a_real_outcome")
            before = connection.execute(
                text("SELECT * FROM scheduled_action_runs ORDER BY id")
            ).all()
            with pytest.raises(RuntimeError, match="Busy routine history"):
                change.downgrade()
            assert (
                connection.execute(text("SELECT * FROM scheduled_action_runs ORDER BY id")).all()
                == before
            )
            assert len(before) == len(original) + 1

    async with async_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.run_sync(check)
        finally:
            await transaction.rollback()
