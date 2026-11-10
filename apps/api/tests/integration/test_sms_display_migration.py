"""Display projection upgrade/downgrade preserves the archive and its accounting."""

import importlib.util
from pathlib import Path
from uuid import UUID

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, func, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.models import SmsMessage, SmsSearchTerm
from src.domains.users.models import User
from tests.integration.test_application_memory_independent_transactions import (
    committed_actor as committed_actor,
)
from tests.integration.test_sms_ingestion import authority, message

pytestmark = pytest.mark.integration


async def test_display_index_migration_round_trip(
    async_engine: AsyncEngine, committed_actor: UUID
) -> None:
    async with AsyncSession(async_engine, expire_on_commit=False) as seed:
        user = await seed.get(User, committed_actor)
        assert user is not None
        actor = await authority(seed, user)
        await SmsIngestionService(seed).ingest(actor, [message(body="Migration Café 東京")])
        stored = await seed.scalar(
            select(SmsMessage.logical_bytes).where(SmsMessage.user_id == committed_actor)
        )
        hashes = await seed.scalar(
            select(func.cardinality(SmsSearchTerm.display_hashes)).where(
                SmsSearchTerm.user_id == committed_actor
            )
        )
        assert stored is not None and hashes is not None and hashes > 0
        await seed.commit()
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic/versions/2026_11_09_0400-c83a51f09d62_sms_display_index.py"
    )
    spec = importlib.util.spec_from_file_location("display_index_migration", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    def cycle(connection: Connection) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            assert (
                connection.scalar(
                    text("SELECT logical_bytes FROM sms_messages WHERE user_id = :owner"),
                    {"owner": committed_actor},
                )
                == stored - 32 * hashes
            )
            assert "display_hashes" not in {
                c["name"] for c in inspect(connection).get_columns("sms_search_terms")
            }
            migration.upgrade()
        columns = {c["name"]: c for c in inspect(connection).get_columns("sms_search_terms")}
        assert columns["display_hashes"]["nullable"] and columns["display_version"]["nullable"]
        assert not columns["display_complete"]["nullable"]
        assert "ix_sms_display_terms_gin" in {
            i["name"] for i in inspect(connection).get_indexes("sms_search_terms")
        }
        assert (
            connection.scalar(text("SELECT COUNT(*) FROM sms_search_terms WHERE display_complete"))
            == 0
        )

    async with async_engine.begin() as connection:
        await connection.run_sync(cycle)
