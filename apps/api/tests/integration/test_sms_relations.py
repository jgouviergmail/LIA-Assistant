"""Real source aggregates and freshness for Relations, never counts from pages."""

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.relations.identity import IdentityResolver
from src.domains.sms.identity import ContactIdentity, IdentityBook
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.relation_reader import SmsRelationReader
from src.domains.users.models import User
from tests.integration.test_application_memory_independent_transactions import (
    committed_actor as committed_actor,
)
from tests.integration.test_sms_ingestion import authority, message

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def sms_actor_session(async_engine, committed_actor):
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        actor = await db.get(User, committed_actor)
        yield db, actor


async def test_relation_counts_all_senders_once_and_details_only_matching_identity(
    sms_actor_session, monkeypatch
):
    db_session, test_user = sms_actor_session
    principal = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(
        principal,
        [message(sender="+33612345678", body=f"Repas {i}") for i in range(4)]
        + [message(sender="Papa", body="Visite"), message(sender="Autre", body="Autre personne")],
    )
    book = IdentityBook(
        contacts=(ContactIdentity("Alice", numbers=("+33612345678",)),),
        complete=True,
        relations={"alice": "Alice"},
        resolver=IdentityResolver.from_pairs([("papa", "alice")]),
    )
    directory = AsyncMock(return_value=book)
    monkeypatch.setattr("src.domains.sms.relation_reader.load_identity_book", directory)
    reader = SmsRelationReader()
    page = await reader.read(test_user.id, person="Alice", limit=2, assistant=False)
    assert page.available and page.total == 5 and len(page.messages) == 2
    assert sum(item.count for item in page.activities) == 6
    assert all(item.body != "Autre personne" for item in page.messages)
    assert directory.await_count == 1
    directory.return_value = IdentityBook(contacts=book.contacts, complete=True)
    unmerged = await reader.read(test_user.id, person="Alice", limit=2, assistant=False)
    assert unmerged.total == 4 and sum(item.count for item in unmerged.activities) == 6

    with pytest.raises(ResourceConflictError):
        await reader.check(db_session, test_user.id, page)
    await db_session.rollback()
    with pytest.raises(AuthorizationError):
        await reader.read(test_user.id, person="Alice", assistant=True)


async def test_new_sms_and_withdrawal_refuse_old_relation_evidence(sms_actor_session, monkeypatch):
    db_session, test_user = sms_actor_session
    principal = await authority(db_session, test_user)
    test_user.sms_preferences = {"assistant_enabled": True}
    await db_session.commit()
    await SmsIngestionService(db_session).ingest(principal, [message(sender="Alice", body="Avant")])
    monkeypatch.setattr(
        "src.domains.sms.relation_reader.load_identity_book",
        AsyncMock(return_value=IdentityBook(complete=True)),
    )
    reader = SmsRelationReader()
    page = await reader.read(test_user.id, person="Alice", assistant=True)
    await SmsIngestionService(db_session).ingest(principal, [message(sender="Alice", body="Après")])
    with pytest.raises(ResourceConflictError):
        await reader.check(db_session, test_user.id, page)
    await db_session.rollback()
    await db_session.refresh(test_user)
    test_user.sms_preferences = {"assistant_enabled": False}
    await db_session.commit()
    with pytest.raises(AuthorizationError):
        await reader.check(db_session, test_user.id, page)


async def test_directory_budget_never_turns_capped_senders_into_exact_totals(
    sms_actor_session, monkeypatch
):
    from src.core.config import settings
    from src.domains.shared.relation_sms import read_relation_sms, register_relation_sms_reader

    db, actor = sms_actor_session
    principal = await authority(db, actor)
    await SmsIngestionService(db).ingest(
        principal, [message(sender="Alice"), message(sender="Bob")]
    )
    monkeypatch.setattr(settings, "sms_directory_max_contacts", 1)
    directory = AsyncMock()
    monkeypatch.setattr("src.domains.sms.relation_reader.load_identity_book", directory)
    with pytest.raises(ResourceConflictError):
        await SmsRelationReader().read(actor.id)
    directory.assert_not_awaited()
    register_relation_sms_reader(SmsRelationReader)
    page = await read_relation_sms(actor.id)
    assert not page.available and page.proof is None and not page.activities


async def test_relation_sql_budget_refuses_slow_source_without_retaining_owner_lock(
    sms_actor_session, async_engine, monkeypatch
):
    from sqlalchemy import func, select

    from src.core.config import settings
    from src.domains.shared.relation_sms import read_relation_sms, register_relation_sms_reader
    from src.domains.sms import relation_reader

    db, actor = sms_actor_session
    owner = actor.id
    await db.commit()
    original = relation_reader.source_stamp

    async def slow(session, identity):
        await session.execute(select(func.pg_sleep(0.15)))
        return await original(session, identity)

    monkeypatch.setattr(settings, "sms_search_timeout_ms", 30)
    monkeypatch.setattr(relation_reader, "source_stamp", slow)
    register_relation_sms_reader(SmsRelationReader)
    page = await read_relation_sms(owner)
    assert not page.available
    async with AsyncSession(async_engine) as observer:
        assert (
            await observer.scalar(
                select(User.id).where(User.id == owner).with_for_update(nowait=True)
            )
            == owner
        )


async def test_relation_resolution_budget_refuses_instead_of_truncating(monkeypatch):
    from src.core.security.utils import encrypt_data

    monkeypatch.setattr(
        "src.domains.sms.relation_reader.perf_counter",
        __import__("unittest.mock").mock.Mock(side_effect=[0, 100]),
    )
    with pytest.raises(ResourceConflictError):
        await SmsRelationReader._resolve(
            [("hash", encrypt_data("Alice"), 137, None)], IdentityBook(complete=True), None
        )
