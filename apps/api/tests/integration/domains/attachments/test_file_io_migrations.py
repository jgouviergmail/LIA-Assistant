"""Populated rollback cannot discard unknown writers or confirmed deletion witnesses."""

import importlib.util
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration


async def test_account_fences_and_writers_refuse_populated_rollback(
    async_engine: AsyncEngine,
) -> None:
    fence = _migration("2026_11_10_1845-e36f8a0b2c49_account_cleanup_fence.py")
    writers = _migration("2026_11_10_1910-f4709b1c3d50_account_file_writers.py")

    def exercise(connection: Connection) -> None:
        schema = f"account_io_{uuid4().hex}"
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        connection.execute(
            text("CREATE TABLE users(id uuid PRIMARY KEY, is_active bool, deleted_at timestamptz)")
        )
        owner = uuid4()
        connection.execute(text("INSERT INTO users VALUES (:id, false, NULL)"), {"id": owner})
        with Operations.context(MigrationContext.configure(connection)):
            fence.upgrade()
            writers.upgrade()
            connection.execute(text("UPDATE users SET deletion_started_at=now()"))
            with pytest.raises(RuntimeError, match="pending account cleanup"):
                fence.downgrade()
            writer = uuid4()
            connection.execute(
                text("INSERT INTO account_file_writers(id, user_id, worker_id) VALUES (:id,:u,:w)"),
                {"id": writer, "u": owner, "w": uuid4()},
            )
            with pytest.raises(RuntimeError, match="file writers"):
                writers.downgrade()
            # Even an out-of-band account removal cannot erase the recovery coordinate.
            connection.execute(text("DELETE FROM users"))
            assert connection.scalar(text("SELECT id FROM account_file_writers")) == writer
            assert not inspect(connection).get_foreign_keys("account_file_writers")
            connection.execute(text("DELETE FROM account_file_writers"))
            writers.downgrade()
            fence.downgrade()
            fence.upgrade()
            writers.upgrade()

    async with async_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.run_sync(exercise)
        finally:
            await transaction.rollback()


def _migration(name: str) -> ModuleType:
    path = Path(__file__).resolve().parents[4] / "alembic" / "versions" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_populated_io_and_witness_migrations_preserve_pending_work(
    async_engine: AsyncEngine,
) -> None:
    io = _migration("2026_11_10_1630-b03c5d7e9f16_attachment_io_ownership.py")
    witness = _migration("2026_11_10_1700-c14d6e8f0a27_attachment_removal_witness.py")

    def exercise(connection: Connection) -> None:
        schema = f"file_io_{uuid4().hex}"
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        connection.execute(
            text("CREATE TABLE attachments(id uuid PRIMARY KEY, status text NOT NULL)")
        )
        connection.execute(
            text("INSERT INTO attachments VALUES (:id, 'uploaded')"), {"id": uuid4()}
        )
        with Operations.context(MigrationContext.configure(connection)):
            io.upgrade()
            witness.upgrade()
            assert connection.scalar(text("SELECT io_fence FROM attachments")) == 0
            assert (
                connection.scalar(text("SELECT deletion_check_identity FROM attachments")) is False
            )
            connection.execute(
                text("UPDATE attachments SET io_owner_token=:token"), {"token": uuid4()}
            )
            with pytest.raises(RuntimeError, match="unfinished"):
                io.downgrade()
            connection.execute(text("UPDATE attachments SET deletion_check_identity=true"))
            with pytest.raises(RuntimeError, match="deletion identity"):
                witness.downgrade()
            # No SQL error aborted the transaction, and neither refusal lost evidence.
            columns = {column["name"] for column in inspect(connection).get_columns("attachments")}
            assert {
                "io_owner_token",
                "deletion_check_identity",
                "deletion_expected_digest",
            } <= columns
            connection.execute(
                text("UPDATE attachments SET deletion_check_identity=false, io_owner_token=NULL")
            )
            witness.downgrade()
            io.downgrade()
            assert {
                column["name"] for column in inspect(connection).get_columns("attachments")
            } == {"id", "status"}
            io.upgrade()
            witness.upgrade()
            assert connection.scalar(text("SELECT count(*) FROM attachments")) == 1

    async with async_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.run_sync(exercise)
        finally:
            await transaction.rollback()
