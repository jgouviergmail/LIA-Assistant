"""A replacement index is atomic, recoverable and catches concurrent receipts."""

from unittest.mock import patch

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.models import SmsMessage, SmsSearchTerm
from src.domains.users.models import User
from tests.integration.test_application_memory_independent_transactions import (
    committed_actor as committed_actor,
)
from tests.integration.test_sms_ingestion import authority, message

pytestmark = pytest.mark.integration


async def test_rebuild_restores_projection_without_changing_messages(db_session, test_user):
    from src.domains.sms.search_index import rebuild_sms_index

    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(
        actor, [message(body="Café demain 東京"), message(body="Un autre")]
    )
    await db_session.execute(delete(SmsSearchTerm).where(SmsSearchTerm.user_id == test_user.id))
    await db_session.commit()
    count = await rebuild_sms_index(db_session, test_user.id)
    assert count == 2
    assert await db_session.scalar(select(func.count()).select_from(SmsSearchTerm)) == 2
    assert await db_session.scalar(select(func.count()).select_from(SmsMessage)) == 2


async def test_interrupted_rebuild_keeps_the_last_valid_index(db_session, test_user):
    from src.domains.sms import search_index

    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(actor, [message(), message()])
    before = list(
        (await db_session.scalars(select(SmsSearchTerm.id).order_by(SmsSearchTerm.id))).all()
    )
    with patch.object(search_index, "decrypt_data", side_effect=ValueError("unreadable cipher")):
        with pytest.raises(ValueError):
            await search_index.rebuild_sms_index(db_session, test_user.id)
    await db_session.rollback()
    after = list(
        (await db_session.scalars(select(SmsSearchTerm.id).order_by(SmsSearchTerm.id))).all()
    )
    assert after == before


async def test_rebuild_catches_a_write_after_its_first_snapshot(
    async_engine, committed_actor, monkeypatch
):
    from src.domains.sms import search_index

    async with AsyncSession(async_engine, expire_on_commit=False) as seed:
        user = await seed.get(User, committed_actor)
        actor = await authority(seed, user)
        await SmsIngestionService(seed).ingest(actor, [message(body="Avant")])
    original = search_index.stage_messages
    calls = 0

    async def stage(*args, **kwargs):
        nonlocal calls
        count = await original(*args, **kwargs)
        calls += 1
        if calls == 1:
            async with AsyncSession(async_engine, expire_on_commit=False) as writer:
                await SmsIngestionService(writer).ingest(
                    actor, [message(body="Pendant reconstruction 東京")]
                )
        return count

    monkeypatch.setattr(search_index, "stage_messages", stage)
    async with AsyncSession(async_engine, expire_on_commit=False) as rebuild:
        assert await search_index.rebuild_sms_index(rebuild, committed_actor) == 2
    async with AsyncSession(async_engine) as check:
        assert (
            await check.scalar(
                select(func.count())
                .select_from(SmsSearchTerm)
                .where(SmsSearchTerm.user_id == committed_actor)
            )
            == 2
        )


async def test_erasure_after_staging_cannot_restore_messages_index_or_deliveries(
    async_engine, committed_actor, monkeypatch
):
    from src.domains.ingestion.models import IngestionDelivery, IngestionReceipt
    from src.domains.sms import search_index
    from src.domains.sms.management_commands import erase_sms, prepare_sms_erasure
    from src.domains.sms.management_schemas import SmsEraseRequest
    from src.domains.users.preference_cas import PreferenceWriteReceipt

    payload = message(body="Synthetic staged message to erase")
    async with AsyncSession(async_engine, expire_on_commit=False) as seed:
        user = await seed.get(User, committed_actor)
        actor = await authority(seed, user)
        await SmsIngestionService(seed).ingest(actor, [payload])
    original = search_index.stage_messages
    calls = 0

    async def approved():
        return None

    async def stage(*args, **kwargs):
        nonlocal calls
        count = await original(*args, **kwargs)
        calls += 1
        if calls == 1:
            async with AsyncSession(async_engine, expire_on_commit=False) as eraser:
                selection = await prepare_sms_erasure(
                    eraser, committed_actor, SmsEraseRequest(all_messages=True)
                )
                receipt = PreferenceWriteReceipt()
                await erase_sms(eraser, committed_actor, selection, receipt, approved)
                assert receipt.committed
        return count

    monkeypatch.setattr(search_index, "stage_messages", stage)
    async with AsyncSession(async_engine, expire_on_commit=False) as rebuild:
        assert await search_index.rebuild_sms_index(rebuild, committed_actor) == 0
    async with AsyncSession(async_engine, expire_on_commit=False) as check:
        for model in (SmsMessage, SmsSearchTerm):
            assert await check.scalar(select(func.count()).select_from(model)) == 0
        assert (await check.scalar(select(IngestionReceipt))).verdict == "deleted"
        assert (await check.scalar(select(IngestionDelivery))).state == "cancelled"
        assert (await SmsIngestionService(check).ingest(actor, [payload])).duplicate == 1
        assert await check.scalar(select(func.count()).select_from(SmsMessage)) == 0
