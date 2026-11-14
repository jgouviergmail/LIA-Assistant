"""The reasons a routine did not run are enforced by PostgreSQL without rewriting its history.

Two outcomes joined the vocabulary on 2026-11-12, each by its own migration:
``skipped_quota`` (the account's usage ceiling) then ``skipped_late`` (an
occurrence reached past its catch-up window). For each one: the value is
refused before, accepted after, no existing row changes, and a downgrade
refuses to erase rows the older vocabulary cannot read. Once both are applied,
the documented vocabulary is the model's, word for word.
"""

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

from src.domains.scheduled_actions.models import ScheduledActionRun, ScheduledRunOutcome

pytestmark = pytest.mark.integration
_VERSIONS = Path(__file__).resolve().parents[4] / "alembic/versions"
#: The outcomes the table accepted before 2026-11-12, in the order their
#: migrations declared them.
_BEFORE = ("success", "failure", "skipped_condition", "proposed", "skipped_hitl", "skipped_busy")
#: (migration, the outcome it adds, what its downgrade says when it refuses).
_CHAIN = (
    (
        "2026_11_12_1000-1e2baddce0fe_scheduled_run_quota_outcome.py",
        "skipped_quota",
        "Quota routine history",
    ),
    (
        "2026_11_12_1700-7a3c9e51d4b8_scheduled_run_late_outcome.py",
        "skipped_late",
        "Missed routine history",
    ),
)


def _load(filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(filename, _VERSIONS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_each_new_outcome_survives_upgrade_and_refuses_a_lossy_downgrade(
    async_engine: AsyncEngine,
) -> None:
    table = _load("2026_09_05_0200-d8e9f0a1b2c3_scheduled_action_runs.py")
    busy = _load("2026_11_10_1300-e70f2a4b6c83_scheduled_run_busy_outcome.py")
    chain = [(_load(filename), outcome, refusal) for filename, outcome, refusal in _CHAIN]
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

    def refused(connection: Connection, outcome: str) -> None:
        with pytest.raises(IntegrityError):
            with connection.begin_nested():
                insert(connection, outcome)

    def rows(connection: Connection) -> list[tuple[object, ...]]:
        return [
            tuple(row)
            for row in connection.execute(text("SELECT * FROM scheduled_action_runs ORDER BY id"))
        ]

    def check(connection: Connection) -> None:
        schema = f"routine_outcomes_{uuid4().hex}"
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        connection.execute(text("CREATE TABLE users (id uuid PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE scheduled_actions (id uuid PRIMARY KEY)"))
        connection.execute(text("INSERT INTO users VALUES (:id)"), {"id": owner})
        connection.execute(text("INSERT INTO scheduled_actions VALUES (:id)"), {"id": action})
        with Operations.context(MigrationContext.configure(connection)):
            table.upgrade()
            busy.upgrade()
            for outcome in _BEFORE:
                insert(connection, outcome)

            snapshots = []
            for migration, outcome, _refusal in chain:
                before = rows(connection)
                snapshots.append(before)
                refused(connection, outcome)
                migration.upgrade()
                assert rows(connection) == before
                insert(connection, outcome)
                refused(connection, "not_a_real_outcome")

            # The documented vocabulary is the model's, word for word: the
            # replay check compares the two.
            comment = connection.execute(
                text(
                    "SELECT col_description('scheduled_action_runs'::regclass, attnum) "
                    "FROM pg_attribute WHERE attrelid = 'scheduled_action_runs'::regclass "
                    "AND attname = 'outcome'"
                )
            ).scalar_one()
            assert comment == ScheduledActionRun.__table__.c.outcome.comment
            assert comment.split(" | ") == [member.value for member in ScheduledRunOutcome]

            for (migration, outcome, refusal), before in zip(
                reversed(chain), reversed(snapshots), strict=True
            ):
                held = rows(connection)
                with pytest.raises(RuntimeError, match=refusal):
                    migration.downgrade()
                assert rows(connection) == held

                connection.execute(
                    text("DELETE FROM scheduled_action_runs WHERE outcome = :outcome"),
                    {"outcome": outcome},
                )
                migration.downgrade()
                assert rows(connection) == before
                refused(connection, outcome)

    async with async_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.run_sync(check)
        finally:
            await transaction.rollback()
