"""Independent PostgreSQL connections prove the owner fence is real."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthenticationError
from src.domains.ingestion.models import IngestionToken
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.models import SmsMessage
from src.domains.users.models import User
from tests.integration.test_application_memory_independent_transactions import (
    committed_actor as committed_actor,
)
from tests.integration.test_sms_ingestion import authority, message

pytestmark = pytest.mark.integration


async def test_pre_authenticated_writer_waits_for_owner_then_refuses_revoked_token(
    async_engine, committed_actor
):
    async with AsyncSession(async_engine, expire_on_commit=False) as seed:
        user = await seed.get(User, committed_actor)
        actor = await authority(seed, user)
        await seed.commit()
    async with AsyncSession(async_engine, expire_on_commit=False) as manager:
        await manager.scalar(select(User).where(User.id == committed_actor).with_for_update())
        token = await manager.get(IngestionToken, actor.token_id)
        token.revoked_at = datetime.now(UTC)
        await manager.flush()
        async with AsyncSession(async_engine, expire_on_commit=False) as writer:
            assert await writer.scalar(select(func.pg_backend_pid())) != await manager.scalar(
                select(func.pg_backend_pid())
            )
            await writer.execute(text("SET LOCAL lock_timeout = '150ms'"))
            with pytest.raises(DBAPIError) as blocked:
                await SmsIngestionService(writer).ingest(actor, [message()])
            assert getattr(blocked.value.orig, "sqlstate", None) == "55P03"
            await writer.rollback()
            await manager.commit()
            with pytest.raises(AuthenticationError):
                await SmsIngestionService(writer).ingest(actor, [message()])
            assert (
                await writer.scalar(
                    select(func.count())
                    .select_from(SmsMessage)
                    .where(SmsMessage.user_id == committed_actor)
                )
                == 0
            )


async def test_two_connections_accept_same_identity_exactly_once(async_engine, committed_actor):
    import asyncio

    async with AsyncSession(async_engine, expire_on_commit=False) as seed:
        user = await seed.get(User, committed_actor)
        actor = await authority(seed, user)
        await seed.commit()
    payload = message()

    async def deposit():
        async with AsyncSession(async_engine, expire_on_commit=False) as writer:
            return await SmsIngestionService(writer).ingest(actor, [payload])

    results = await asyncio.gather(deposit(), deposit())
    assert sum(result.inserted for result in results) == 1
    assert sum(result.duplicate for result in results) == 1
