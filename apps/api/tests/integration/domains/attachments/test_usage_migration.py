"""The actual file-usage migration decodes archive metadata without inventing ownership."""

import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration

_MIGRATION = Path(__file__).resolve().parents[4] / (
    "alembic/versions/2026_11_10_1600-a92b4c6d8e05_attachment_conversation_usage.py"
)


async def test_real_ddl_backfills_only_owned_message_references(async_engine: AsyncEngine) -> None:
    """Malformed metadata, duplicated references and a source FK are not proof of use."""
    spec = importlib.util.spec_from_file_location("attachment_usage", _MIGRATION)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    owner, foreign_owner, main, annex = (uuid4() for _ in range(4))
    shared, unknown, foreign_file = (uuid4() for _ in range(3))

    def cycle(connection: Connection) -> None:
        schema = f"attachment_usage_{uuid4().hex}"
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        connection.execute(
            text(
                "CREATE TABLE conversations(id uuid PRIMARY KEY, user_id uuid NOT NULL, "
                "revision integer NOT NULL, deleted_at timestamptz)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE attachments(id uuid PRIMARY KEY, user_id uuid NOT NULL, "
                "conversation_id uuid, status text NOT NULL, origin text NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE conversation_messages(id uuid PRIMARY KEY, "
                "conversation_id uuid NOT NULL, message_metadata jsonb)"
            )
        )
        for conversation_id in (main, annex):
            connection.execute(
                text("INSERT INTO conversations VALUES (:id, :owner, 7, NULL)"),
                {"id": conversation_id, "owner": owner},
            )
        for file_id, file_owner in (
            (shared, owner),
            (unknown, owner),
            (foreign_file, foreign_owner),
        ):
            connection.execute(
                text("INSERT INTO attachments VALUES (:id, :owner, :source, 'ready', 'upload')"),
                {"id": file_id, "owner": file_owner, "source": main},
            )
        metadata_rows: list[dict[str, object]] = [
            {"attachments": [{"id": str(shared)}, {"id": str(shared)}]},
            {"attachments": [{"id": str(foreign_file)}, {"id": "invalid"}, {"id": 5}, None]},
            {"attachments": "not an array"},
            {"attachments": {"id": str(unknown)}},
            {"attachments": None},
            {},
        ]
        for discussion in (main, annex):
            for metadata in metadata_rows:
                connection.execute(
                    text(
                        "INSERT INTO conversation_messages VALUES (:id, :conversation, "
                        "CAST(:metadata AS jsonb))"
                    ),
                    {"id": uuid4(), "conversation": discussion, "metadata": json.dumps(metadata)},
                )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            rows = connection.execute(
                text(
                    "SELECT attachment_id, conversation_id, conversation_revision "
                    "FROM conversation_attachment_usages"
                )
            ).all()
            assert {tuple(row) for row in rows} == {(shared, main, 7), (shared, annex, 7)}
            assert connection.scalar(text("SELECT count(*) FROM attachments")) == 3
            connection.execute(
                text(
                    "UPDATE attachments SET status='deleting', deletion_reason='conversation_reset' "
                    "WHERE id=:id"
                ),
                {"id": shared},
            )
            with pytest.raises(RuntimeError, match="cleanup evidence"):
                migration.downgrade()
            connection.execute(text("UPDATE attachments SET status='ready'"))
            migration.downgrade()
            assert "conversation_attachment_usages" not in inspect(connection).get_table_names()
            migration.upgrade()
            assert (
                connection.scalar(text("SELECT count(*) FROM conversation_attachment_usages")) == 2
            )
            connection.execute(text("DELETE FROM conversations WHERE id=:id"), {"id": main})
            assert (
                connection.scalar(text("SELECT count(*) FROM conversation_attachment_usages")) == 1
            )
            connection.execute(text("DELETE FROM attachments WHERE id=:id"), {"id": shared})
            assert (
                connection.scalar(text("SELECT count(*) FROM conversation_attachment_usages")) == 0
            )

    async with async_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.run_sync(cycle)
        finally:
            await transaction.rollback()
