"""The actual frozen Alembic revision must recreate its ORM contract."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import CheckConstraint, inspect

from src.infrastructure.database.session import Base

pytestmark = pytest.mark.integration


async def test_sms_migration_round_trip_matches_columns_and_indexes(async_engine):
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic/versions/2026_10_19_2000-1c294a7e820f_phone_ingestion_sms.py"
    )
    spec = importlib.util.spec_from_file_location("sms_migration", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    next_path = path.parent / "2026_10_20_0118-3fd106ace921_sms_proactive.py"
    next_spec = importlib.util.spec_from_file_location("sms_proactive_migration", next_path)
    assert next_spec and next_spec.loader
    proactive = importlib.util.module_from_spec(next_spec)
    next_spec.loader.exec_module(proactive)
    names = {
        "ingestion_sources",
        "ingestion_tokens",
        "ingestion_receipts",
        "ingestion_deliveries",
        "sms_messages",
        "sms_search_terms",
        "sms_sender_blocks",
    }

    def cycle(connection):
        with Operations.context(MigrationContext.configure(connection)):
            proactive.downgrade()
            migration.downgrade()
            assert not names & set(inspect(connection).get_table_names())
            migration.upgrade()
            proactive.upgrade()
        reflection = inspect(connection)
        for name in names:
            assert {column["name"] for column in reflection.get_columns(name)} == set(
                Base.metadata.tables[name].columns.keys()
            )
            assert {
                index["name"]
                for index in reflection.get_indexes(name)
                if not index.get("duplicates_constraint")
            } == {index.name for index in Base.metadata.tables[name].indexes}
            model = Base.metadata.tables[name]
            expected_foreign_keys = {
                (
                    tuple(fk.column_keys),
                    fk.referred_table.name,
                    tuple(element.column.name for element in fk.elements),
                    fk.ondelete,
                )
                for fk in model.foreign_key_constraints
            }
            actual_foreign_keys = {
                (
                    tuple(fk["constrained_columns"]),
                    fk["referred_table"],
                    tuple(fk["referred_columns"]),
                    fk["options"].get("ondelete"),
                )
                for fk in reflection.get_foreign_keys(name)
            }
            assert actual_foreign_keys == expected_foreign_keys
            assert {check["name"] for check in reflection.get_check_constraints(name)} == {
                constraint.name
                for constraint in model.constraints
                if isinstance(constraint, CheckConstraint)
            }
        assert {"sms_preferences", "ingestion_key_encrypted"} <= {
            column["name"] for column in reflection.get_columns("users")
        }

    async with async_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.run_sync(cycle)
        finally:
            await transaction.rollback()
