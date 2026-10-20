"""Publication rechecks after detached provider I/O on independent SQL sessions."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.sms.facade import SmsFacade
from src.domains.sms.identity import IdentityBook
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.management_commands import erase_sms, prepare_sms_erasure
from src.domains.sms.management_schemas import SmsEraseRequest
from src.domains.sms.read_schemas import SmsQuery
from src.domains.users.extraction_consent import invalidate_extractions
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.test_application_memory_independent_transactions import (
    committed_actor as committed_actor,
)
from tests.integration.test_sms_ingestion import authority, message

pytestmark = pytest.mark.integration


async def test_withdrawal_wins_before_assistant_publication(
    async_engine, committed_actor, monkeypatch
):
    async with AsyncSession(async_engine, expire_on_commit=False) as seed:
        user = await seed.get(User, committed_actor)
        user.sms_preferences = {"assistant_enabled": True}
        actor = await authority(seed, user)
        await SmsIngestionService(seed).ingest(actor, [message()])

    async def detached_lookup(owner):
        async with AsyncSession(async_engine, expire_on_commit=False) as manager:
            await manager.execute(text("SET LOCAL lock_timeout='150ms'"))
            user = await manager.scalar(select(User).where(User.id == owner).with_for_update())
            user.sms_preferences = {"assistant_enabled": False}
            invalidate_extractions(user)
            await manager.commit()
        return IdentityBook()

    monkeypatch.setattr("src.domains.sms.facade.load_identity_book", detached_lookup)
    async with AsyncSession(async_engine, expire_on_commit=False) as reader:
        with pytest.raises(AuthorizationError):
            await SmsFacade(reader).list(committed_actor, SmsQuery(), assistant=True)


async def test_erasure_wins_before_a_prepared_page_is_published(
    async_engine, committed_actor, monkeypatch
):
    async with AsyncSession(async_engine, expire_on_commit=False) as seed:
        user = await seed.get(User, committed_actor)
        actor = await authority(seed, user)
        await SmsIngestionService(seed).ingest(actor, [message()])

    async def check():
        return None

    async def detached_lookup(owner):
        async with AsyncSession(async_engine, expire_on_commit=False) as manager:
            await manager.execute(text("SET LOCAL lock_timeout='150ms'"))
            selected = await prepare_sms_erasure(manager, owner, SmsEraseRequest(all_messages=True))
            await erase_sms(manager, owner, selected, PreferenceWriteReceipt(), check)
        return IdentityBook()

    monkeypatch.setattr("src.domains.sms.facade.load_identity_book", detached_lookup)
    async with AsyncSession(async_engine, expire_on_commit=False) as reader:
        with pytest.raises(ResourceConflictError):
            await SmsFacade(reader).list(committed_actor, SmsQuery(), assistant=False)
