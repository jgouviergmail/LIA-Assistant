"""An already-stamped early dev schema converges without erasing execution authority."""

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Literal
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.conversation_execution import ExecutionKind, RunAdmission
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.reservation_repository import ConversationReservationRepository
from tests.fixtures.learning_sources import Sources
from tests.fixtures.learning_sources import sources as sources

pytestmark = pytest.mark.integration
_VERSIONS = Path(__file__).resolve().parents[4] / "alembic/versions"


def _migration(filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(filename, _VERSIONS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("early_schema", [True, False])
async def test_repair_retains_rows_fences_and_existing_transport_authority(
    async_engine: AsyncEngine, early_schema: bool
) -> None:
    parent = _migration("2026_11_10_0800-c58d9e2f4a61_conversation_execution_authority.py")
    repair = _migration("2026_11_10_1200-d69e1f3a5b72_complete_execution_transport_fields.py")
    owner, activity, conversation, token, worker = (uuid4() for _ in range(5))

    def check(connection: Connection) -> None:
        schema = f"execution_transport_{uuid4().hex}"
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        connection.execute(text("CREATE TABLE users (id uuid PRIMARY KEY)"))
        connection.execute(text("INSERT INTO users VALUES (:owner)"), {"owner": owner})
        with Operations.context(MigrationContext.configure(connection)):
            parent.upgrade()
            if early_schema:
                connection.execute(
                    text("ALTER TABLE conversation_executions DROP COLUMN cancellable")
                )
                connection.execute(text("DROP INDEX uq_conversation_execution_owner_stream"))
            columns = "" if early_schema else ", cancellable"
            values = "" if early_schema else ", true"
            connection.execute(
                text(
                    "INSERT INTO conversation_executions "
                    "(id,user_id,conversation_id,conversation_revision,runtime_id,conversation_kind,"
                    "kind,phase,owner_token,worker_id,run_id,stream_id,relayed,heartbeat_at,"
                    f"created_at,updated_at{columns}) VALUES "
                    "(:id,:owner,:conversation,7,:conversation,'secondary','graph','running',"
                    f":token,:worker,'run','stream',false,now(),now(),now(){values})"
                ),
                {
                    "id": activity,
                    "owner": owner,
                    "conversation": conversation,
                    "token": token,
                    "worker": worker,
                },
            )
            original = connection.execute(
                text("SELECT id,owner_token,worker_id,fence,phase FROM conversation_executions")
            ).one()
            repair.upgrade()
            repair.upgrade()
            assert (
                connection.scalar(text("SELECT cancellable FROM conversation_executions"))
                is not early_schema
            )
            assert (
                connection.execute(
                    text("SELECT id,owner_token,worker_id,fence,phase FROM conversation_executions")
                ).one()
                == original
            )
            indexes = {
                index["name"]: index
                for index in inspect(connection).get_indexes("conversation_executions")
            }
            assert indexes["uq_conversation_execution_owner_stream"]["unique"]
            assert indexes["uq_conversation_execution_owner_stream"]["column_names"] == [
                "user_id",
                "stream_id",
            ]
            repair.downgrade()
            assert "cancellable" in {
                column["name"]
                for column in inspect(connection).get_columns("conversation_executions")
            }
            with pytest.raises(RuntimeError, match="active conversation executions"):
                parent.downgrade()

    async with async_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.run_sync(check)
        finally:
            await transaction.rollback()


@pytest.mark.parametrize("state", ["idle", "working", "closed"])
async def test_live_work_downgrade_requires_the_whole_voice_reservation_to_be_closed(
    async_engine: AsyncEngine,
    sources: Sources,
    state: Literal["idle", "working", "closed"],
) -> None:
    """An idle open voice session still needs the work table after the rollback."""
    migration = _migration("2026_11_10_2115-a5810c2d4e61_live_reservation_work.py")
    async with AsyncSession(async_engine) as db:
        admission = await ConversationExecutionRepository(db).admit(
            sources.annex,
            run_id=uuid4().hex,
            stream_id=uuid4().hex,
            worker_id=uuid4(),
            kind=ExecutionKind.LIVE,
        )
        assert isinstance(admission, RunAdmission)
        repo = ConversationReservationRepository(db)
        if state == "working":
            await repo.begin(admission, worker_id=uuid4(), purpose="request")
        elif state == "closed":
            closing = await repo.begin_closing(admission, worker_id=uuid4())
            await repo.finish(closing)
        await db.commit()

    def downgrade(connection: Connection) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            if state == "closed":
                migration.downgrade()
                assert not inspect(connection).has_table("conversation_reservation_work")
            else:
                with pytest.raises(RuntimeError, match="Live reservation"):
                    migration.downgrade()
                assert inspect(connection).has_table("conversation_reservation_work")

    async with async_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.run_sync(downgrade)
        finally:
            await transaction.rollback()
