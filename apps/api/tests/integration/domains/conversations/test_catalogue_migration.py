"""Exercise the shipped DDL and its lossless rollback boundary on PostgreSQL."""

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration
_MIGRATION = Path(__file__).resolve().parents[4] / (
    "alembic/versions/2026_11_10_0400-b43c6d9e1a72_secondary_conversations.py"
)


async def test_cleanup_migration_keeps_debt_and_retry_receipts_after_source_deletion(
    async_engine: AsyncEngine,
) -> None:
    path = _MIGRATION.parent / "2026_11_10_1800-d25e7f9a1b38_conversation_operations.py"
    spec = importlib.util.spec_from_file_location("conversation_operations_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def cycle(connection: Connection) -> None:
        schema = f"cleanup_migration_{uuid4().hex}"
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        owner = uuid4()
        connection.execute(text("CREATE TABLE users (id uuid PRIMARY KEY)"))
        connection.execute(text("INSERT INTO users VALUES (:id)"), {"id": owner})
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            connection.execute(
                text(
                    "INSERT INTO conversation_operations "
                    "(id, user_id, request_id, conversation_id, action, conversation_kind, "
                    "old_revision, new_revision, runtime_id, attachment_ids, previous_message_count, "
                    "state, phase, fence, attempts, created_at, updated_at) "
                    "VALUES (:id, :owner, :request, :conversation, 'reset', 'secondary', "
                    "2, 3, :runtime, '{}'::uuid[], 4, 'pending', 'checkpoint', 0, 0, now(), now())"
                ),
                {
                    "id": uuid4(),
                    "owner": owner,
                    "request": uuid4(),
                    "conversation": uuid4(),
                    "runtime": uuid4(),
                },
            )
            connection.execute(text("DELETE FROM users WHERE id=:id"), {"id": owner})
            assert connection.scalar(text("SELECT count(*) FROM conversation_operations")) == 1
            with pytest.raises(RuntimeError, match="retained"):
                migration.downgrade()
            connection.execute(
                text(
                    "UPDATE conversation_operations SET state='succeeded', phase='complete', completed_at=now()"
                )
            )
            with pytest.raises(RuntimeError, match="retained"):
                migration.downgrade()
            connection.execute(text("DELETE FROM conversation_operations"))
            migration.downgrade()
            assert "conversation_operations" not in inspect(connection).get_table_names(
                schema=schema
            )
            migration.upgrade()

    async with async_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.run_sync(cycle)
        finally:
            await transaction.rollback()


async def test_upgrade_preserves_legacy_identity_and_downgrade_refuses_loss(
    async_engine: AsyncEngine,
) -> None:
    """An isolated legacy schema proves backfill, real constraints and retries."""
    spec = importlib.util.spec_from_file_location("secondary_conversations", _MIGRATION)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    owner, primary, secondary = uuid4(), uuid4(), uuid4()

    def cycle(connection: Connection) -> None:
        schema = f"conversation_migration_{uuid4().hex}"
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        connection.execute(text("CREATE TABLE users (id uuid PRIMARY KEY)"))
        connection.execute(
            text(
                "CREATE TABLE conversations (id uuid PRIMARY KEY, user_id uuid NOT NULL "
                "REFERENCES users(id), title varchar(500), deleted_at timestamptz, "
                "CONSTRAINT uq_conversations_user_id UNIQUE(user_id))"
            )
        )
        connection.execute(text("INSERT INTO users(id) VALUES (:id)"), {"id": owner})
        connection.execute(
            text(
                "INSERT INTO conversations(id, user_id, title, deleted_at) "
                "VALUES (:id, :owner, 'Legacy title', now())"
            ),
            {"id": primary, "owner": owner},
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            row = connection.execute(
                text(
                    "SELECT id, runtime_id, kind, revision, title, deleted_at IS NOT NULL "
                    "FROM conversations WHERE id = :id"
                ),
                {"id": primary},
            ).one()
            assert tuple(row) == (primary, primary, "main", 0, "Legacy title", True)

            connection.execute(
                text(
                    "INSERT INTO conversations(id, user_id, runtime_id, kind, title) "
                    "VALUES (:id, :owner, :id, 'secondary', 'Annex')"
                ),
                {"id": secondary, "owner": owner},
            )
            with pytest.raises(RuntimeError, match="Cannot restore singleton"):
                migration.downgrade()
            assert connection.scalar(text("SELECT count(*) FROM conversations")) == 2
            connection.execute(
                text(
                    "INSERT INTO conversation_creation_receipts "
                    "(id, user_id, request_id, payload_hash, conversation_id, created_at, updated_at) "
                    "VALUES (:id, :owner, :attempt, :digest, :result, now(), now())"
                ),
                {
                    "id": uuid4(),
                    "owner": owner,
                    "attempt": uuid4(),
                    "digest": "a" * 64,
                    "result": secondary,
                },
            )
            connection.execute(text("DELETE FROM conversations WHERE id = :id"), {"id": secondary})
            with pytest.raises(RuntimeError, match="Cannot restore singleton"):
                migration.downgrade()
            connection.execute(text("DELETE FROM conversation_creation_receipts"))
            connection.execute(
                text("UPDATE conversations SET runtime_id = :runtime, revision = 1"),
                {"runtime": uuid4()},
            )
            with pytest.raises(RuntimeError, match="Cannot restore singleton"):
                migration.downgrade()
            connection.execute(text("UPDATE conversations SET runtime_id = id, revision = 0"))
            migration.downgrade()
            assert "runtime_id" not in {
                c["name"] for c in inspect(connection).get_columns("conversations")
            }
            assert connection.scalar(text("SELECT id FROM conversations")) == primary
            migration.upgrade()
            assert connection.scalar(text("SELECT runtime_id FROM conversations")) == primary

    async with async_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.run_sync(cycle)
        finally:
            # Roll back the schema itself, including a failed assertion or DDL.
            await transaction.rollback()
