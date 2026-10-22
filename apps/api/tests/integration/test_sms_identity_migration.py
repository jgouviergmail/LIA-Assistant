"""The executable SMS identity migration matches its ORM and is reversible."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import UniqueConstraint, inspect

from src.infrastructure.database.session import Base

pytestmark = pytest.mark.integration


async def test_identity_registry_migration_round_trip(async_engine):
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic/versions/2026_10_21_0010-2c7e893a6d10_sms_sender_identity_registry.py"
    )
    spec = importlib.util.spec_from_file_location("sms_identity_migration", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    names = {"sms_identity_states", "sms_sender_identities"}

    def cycle(connection):
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            assert not names & set(inspect(connection).get_table_names())
            migration.upgrade()
        reflection = inspect(connection)
        for name in names:
            assert {column["name"] for column in reflection.get_columns(name)} == set(
                Base.metadata.tables[name].columns.keys()
            )
            assert {
                tuple(item["column_names"]) for item in reflection.get_unique_constraints(name)
            } == {
                tuple(column.name for column in item.columns)
                for item in Base.metadata.tables[name].constraints
                if isinstance(item, UniqueConstraint)
            }

    async with async_engine.begin() as connection:
        await connection.run_sync(cycle)
