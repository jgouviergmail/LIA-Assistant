"""Native display search preserves encrypted storage and exact owner-scoped pages."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError
from src.domains.ingestion.key_material import key_for_owner
from src.domains.sms import identity_resolution
from src.domains.sms.display_reads import SmsDisplayReader
from src.domains.sms.display_schemas import SmsDisplayQuery
from src.domains.sms.identity import ContactIdentity, IdentityBook
from src.domains.sms.identity_store import reset_resolutions
from src.domains.sms.index_projection import build_index_projection
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.models import SmsMessage, SmsSearchTerm
from src.domains.sms.search_index import rebuild_sms_index
from src.domains.users.models import User
from tests.integration.test_sms_ingestion import authority, message

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("sms_identity_session")]


async def test_display_cursor_rejects_renames_other_owners_and_query_changes(
    db_session: AsyncSession,
    test_user: User,
    test_superuser: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load = AsyncMock(
        return_value=IdentityBook(
            contacts=(ContactIdentity("Alice", numbers=("+33612345678",)),), complete=True
        )
    )
    monkeypatch.setattr(identity_resolution, "load_identity_book", load)
    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(actor, [message(body="one"), message(body="two")])
    reader = SmsDisplayReader(db_session)
    first = await reader.list(test_user.id, SmsDisplayQuery(sort="name", limit=1))
    assert first.next_cursor
    for owner, query in [
        (test_superuser.id, SmsDisplayQuery(sort="name", limit=1, cursor=first.next_cursor)),
        (test_user.id, SmsDisplayQuery(sort="recent", limit=1, cursor=first.next_cursor)),
        (
            test_user.id,
            SmsDisplayQuery(sort="name", query="changed", limit=1, cursor=first.next_cursor),
        ),
    ]:
        with pytest.raises(ResourceConflictError, match="STALE_CURSOR"):
            await reader.list(owner, query)
    await reset_resolutions(db_session, test_user.id)
    load.return_value = IdentityBook(
        contacts=(ContactIdentity("Renamed", numbers=("+33612345678",)),), complete=True
    )
    with pytest.raises(ResourceConflictError, match="STALE_CURSOR"):
        await reader.list(
            test_user.id, SmsDisplayQuery(sort="name", limit=1, cursor=first.next_cursor)
        )
    fresh = await reader.list(test_user.id, SmsDisplayQuery(sort="name", limit=1))
    assert fresh.items[0].display_name == "Renamed"


async def test_oldest_pages_keep_the_insertion_cut_and_exclusive_period_end(
    db_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        identity_resolution,
        "load_identity_book",
        AsyncMock(return_value=IdentityBook(complete=True)),
    )
    actor = await authority(db_session, test_user)
    stamp = datetime.now(UTC) - timedelta(days=4)
    service = SmsIngestionService(db_session)
    await service.ingest(
        actor,
        [message(date=(stamp + timedelta(days=i)).isoformat(), body=f"Day {i}") for i in range(3)],
    )
    reader = SmsDisplayReader(db_session)
    query = SmsDisplayQuery(sort="oldest", limit=1, from_ts=stamp, to_ts=stamp + timedelta(days=2))
    first = await reader.list(test_user.id, query)
    assert first.total == 2 and first.items[0].body == "Day 0"
    await service.ingest(actor, [message(date=stamp.isoformat(), body="Late receipt")])
    second = await reader.list(test_user.id, query.model_copy(update={"cursor": first.next_cursor}))
    assert second.total == 2 and second.items[0].body == "Day 1"
    assert second.next_cursor is None


async def test_rebuild_counts_both_indexes_and_refuses_over_quota_without_swapping(
    db_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = test_user.id
    actor = await authority(db_session, test_user)
    payload = message(body="Été 東京 Bonjour")
    result = await SmsIngestionService(db_session).ingest(actor, [payload])
    identifier = result.items[0].message_id
    projection = build_index_projection(
        test_user.id, payload["sender"], payload["body"], key=key_for_owner(test_user)
    )
    row = await db_session.get(SmsMessage, identifier)
    assert row is not None and row.logical_bytes == projection.logical_bytes
    before = (
        await db_session.execute(select(SmsSearchTerm.id, SmsSearchTerm.display_hashes))
    ).one()
    await db_session.commit()
    with monkeypatch.context() as scoped:
        scoped.setattr(settings, "sms_archive_max_logical_bytes", projection.logical_bytes - 1)
        with pytest.raises(ResourceConflictError, match="INDEX_REBUILD_INCOMPLETE"):
            await rebuild_sms_index(db_session, owner)
    assert (
        await db_session.execute(select(SmsSearchTerm.id, SmsSearchTerm.display_hashes))
    ).one() == before
    await db_session.commit()
    assert await rebuild_sms_index(db_session, owner) == 1
    await db_session.refresh(row)
    assert row.logical_bytes == projection.logical_bytes


async def test_distinct_sender_budget_and_missing_index_are_honest_bounds(
    db_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        identity_resolution,
        "load_identity_book",
        AsyncMock(return_value=IdentityBook(complete=True)),
    )
    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(
        actor, [message(sender="A", body="Bonjour"), message(sender="B", body="Autre")]
    )
    reader = SmsDisplayReader(db_session)
    with monkeypatch.context() as scoped:
        scoped.setattr(settings, "sms_display_max_senders", 1)
        with pytest.raises(ResourceConflictError, match="QUERY_TOO_BROAD"):
            await reader.list(test_user.id, SmsDisplayQuery(sort="name"))
        assert (await reader.list(test_user.id, SmsDisplayQuery())).total == 2
    for projection in (await db_session.scalars(select(SmsSearchTerm))).all():
        projection.display_version = None
        projection.display_hashes = None
    await db_session.commit()
    assert (await reader.list(test_user.id, SmsDisplayQuery(query="bonj"))).total == 1


async def test_display_fragments_and_candidate_false_positives(
    db_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        identity_resolution,
        "load_identity_book",
        AsyncMock(return_value=IdentityBook(complete=True)),
    )
    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(
        actor, [message(body=body) for body in ("Bonjour Café 100%_", "abc---bcd", "abcd", "東京")]
    )
    reader = SmsDisplayReader(db_session)
    for query, expected in [
        ("bonj", "Bonjour Café 100%_"),
        ("100%_", "Bonjour Café 100%_"),
        ("abcd", "abcd"),
        ("京", "東京"),
    ]:
        page = await reader.list(test_user.id, SmsDisplayQuery(query=query))
        assert page.total == 1 and page.items[0].body == expected
    indexes = list((await db_session.scalars(select(SmsSearchTerm))).all())
    for row in indexes:
        row.display_complete = False
        row.display_hashes = []
    await db_session.commit()
    page = await reader.list(test_user.id, SmsDisplayQuery(query="bonj"))
    assert page.total == 1


async def test_many_messages_from_one_matching_sender_do_not_spend_the_body_candidate_budget(
    db_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    book = IdentityBook(
        contacts=(ContactIdentity("Élodie", numbers=("+33612345678",)),), complete=True
    )
    load = AsyncMock(return_value=book)
    monkeypatch.setattr(identity_resolution, "load_identity_book", load)
    actor = await authority(db_session, test_user)
    amount = settings.sms_search_max_candidates + 1
    service = SmsIngestionService(db_session)
    for start in range(0, amount, settings.ingestion_max_batch_items):
        await service.ingest(
            actor,
            [
                message(body="Same words")
                for _ in range(min(settings.ingestion_max_batch_items, amount - start))
            ],
        )
    await service.ingest(actor, [message(sender="Bob", body="elodie in body")])
    reader = SmsDisplayReader(db_session)
    first = await reader.list(test_user.id, SmsDisplayQuery(query="elodie", sort="name", limit=2))
    assert first.total == amount + 1 and first.next_cursor
    assert first.items[0].sender == "Bob"
    next_page = await reader.list(
        test_user.id,
        SmsDisplayQuery(query="elodie", sort="name", limit=2, cursor=first.next_cursor),
    )
    assert next_page.total == first.total
    assert not ({row.id for row in first.items} & {row.id for row in next_page.items})
    load.assert_awaited_once()
    monkeypatch.setattr(settings, "sms_search_max_candidates", 1)
    with pytest.raises(ResourceConflictError, match="QUERY_TOO_BROAD"):
        await reader.list(test_user.id, SmsDisplayQuery(query="Sa"))
