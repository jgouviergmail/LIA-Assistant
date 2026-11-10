"""Native display reads release SQL before identity I/O and fence publication."""

import asyncio
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError
from src.domains.relations.models import RelationFavorite
from src.domains.sms.display_reads import SmsDisplayReader
from src.domains.sms.display_schemas import SmsDisplayQuery
from src.domains.sms.identity import IdentityBook
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.management_commands import erase_sms, prepare_sms_erasure
from src.domains.sms.management_schemas import SmsEraseRequest
from src.domains.sms.search_limits import search_sql_budget
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.test_application_memory_independent_transactions import (
    assert_independent_lock_control,
)
from tests.integration.test_application_memory_independent_transactions import (
    committed_actor as committed_actor,
)
from tests.integration.test_sms_ingestion import authority, message

pytestmark = pytest.mark.integration


async def test_cancelled_search_preserves_cancellation_and_releases_its_transaction(
    async_engine: AsyncEngine,
) -> None:
    async with AsyncSession(async_engine) as reader:
        previous = await reader.scalar(select(func.current_setting("statement_timeout")))
        await reader.commit()
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.05):
                async with search_sql_budget(reader):
                    await reader.execute(text("SELECT pg_sleep(2)"))
        assert not reader.in_transaction()
        assert await reader.scalar(select(func.current_setting("statement_timeout"))) == previous


async def test_database_timeout_is_an_explicit_bound_not_an_empty_page(
    async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "sms_search_timeout_ms", 100)
    async with AsyncSession(async_engine) as reader:
        with pytest.raises(ResourceConflictError, match="QUERY_TOO_BROAD"):
            async with search_sql_budget(reader):
                await reader.execute(text("SELECT pg_sleep(2)"))
        assert not reader.in_transaction()


@pytest.mark.parametrize("sort", ["recent", "name"])
async def test_erasure_during_identity_lookup_refuses_publication_on_distinct_connections(
    async_engine: AsyncEngine, committed_actor: UUID, monkeypatch: pytest.MonkeyPatch, sort: str
) -> None:
    async with AsyncSession(async_engine, expire_on_commit=False) as seed:
        user = await seed.get(User, committed_actor)
        assert user is not None
        actor = await authority(seed, user)
        await SmsIngestionService(seed).ingest(actor, [message()])

    async with AsyncSession(async_engine, expire_on_commit=False) as reader:
        await assert_independent_lock_control(reader, async_engine, committed_actor)
        pid = await reader.scalar(select(func.pg_backend_pid()))
        await reader.commit()

        async def check() -> None:
            return None

        async def lookup(owner: UUID, *, cache_scope: str | None = None) -> IdentityBook:
            assert not reader.in_transaction()
            async with AsyncSession(async_engine, expire_on_commit=False) as manager:
                held = await manager.execute(
                    text(
                        "SELECT state, xact_start FROM pg_stat_activity "
                        "WHERE pid = :pid AND pid <> pg_backend_pid()"
                    ),
                    {"pid": pid},
                )
                for state, started in held:
                    assert state == "idle" and started is None
                await manager.execute(text("SET LOCAL lock_timeout='150ms'"))
                prepared = await prepare_sms_erasure(
                    manager, owner, SmsEraseRequest(all_messages=True)
                )
                await erase_sms(manager, owner, prepared, PreferenceWriteReceipt(), check)
            return IdentityBook(complete=True)

        monkeypatch.setattr("src.domains.sms.identity_resolution.load_identity_book", lookup)
        with pytest.raises(ResourceConflictError):
            await SmsDisplayReader(reader).list(
                committed_actor, SmsDisplayQuery.model_validate({"sort": sort})
            )


async def test_local_relation_rename_invalidates_sorted_continuation_without_contact_refresh(
    async_engine: AsyncEngine, committed_actor: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    contacts = AsyncMock(return_value=IdentityBook(complete=True))
    monkeypatch.setattr("src.domains.sms.identity_resolution.load_identity_book", contacts)
    async with AsyncSession(async_engine, expire_on_commit=False) as seed:
        user = await seed.get(User, committed_actor)
        assert user is not None
        actor = await authority(seed, user)
        await SmsIngestionService(seed).ingest(
            actor, [message(sender="alpha"), message(sender="charlie")]
        )
        favorite = RelationFavorite(user_id=committed_actor, name_key="alpha", display_name="Alpha")
        seed.add(favorite)
        await seed.commit()
        favorite_id = favorite.id
    async with AsyncSession(async_engine, expire_on_commit=False) as reader:
        query = SmsDisplayQuery(sort="name", limit=1)
        page = await SmsDisplayReader(reader).list(committed_actor, query)
        assert page.items[0].display_name == "Alpha" and page.next_cursor
        await reader.commit()
    async with AsyncSession(async_engine, expire_on_commit=False) as writer:
        row = await writer.get(RelationFavorite, favorite_id)
        assert row is not None
        row.display_name = "Zulu"
        await writer.commit()
    async with AsyncSession(async_engine, expire_on_commit=False) as reader:
        with pytest.raises(ResourceConflictError, match="STALE_CURSOR"):
            await SmsDisplayReader(reader).list(
                committed_actor, query.model_copy(update={"cursor": page.next_cursor})
            )
        await reader.rollback()
        fresh = await SmsDisplayReader(reader).list(committed_actor, query)
        assert fresh.items[0].display_name == "charlie"
    contacts.assert_awaited_once()
