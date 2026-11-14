"""A queued Redis learning write cannot outlive its admitted source generation."""

import asyncio
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.core.conversation_execution import RunAdmission, RunEnd
from src.core.run_authority import RunAuthority, run_authority_scope
from src.domains.agents.services.recurrence_ledger import record_occurrence
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.lifecycle import ConversationLifecycle
from src.domains.habits.forgetting import clear_habit_advisory_state
from src.domains.habits.preference_commands import (
    HabitSettingsCompletionUnknown,
    update_habit_settings,
)
from src.domains.habits.schemas import HabitsSettingsUpdate
from src.infrastructure.cache import recurrence_store
from src.infrastructure.streaming import runtime_redis

pytestmark = pytest.mark.integration
DAY = date(2026, 11, 10)


@pytest.fixture(autouse=True)
def source_session(async_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    """Use the admission fixture's committed SQL session factory at the write gate."""

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine) as db:
            yield db
            await db.commit()

    monkeypatch.setattr("src.domains.agents.services.recurrence_ledger.get_db_context", session)


class DelayedWrite:
    """Pause the actual write command; every storage operation reaches real Redis."""

    def __init__(self, redis: Redis) -> None:
        self.redis = redis
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def get(self, key: str) -> object:
        return await self.redis.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> object:
        self.started.set()
        await self.release.wait()
        return await self.redis.set(key, value, ex=ex)

    def eval(self, script: str, numkeys: int, /, *args: str) -> Awaitable[object]:
        return self._eval(script, numkeys, args)

    async def _eval(self, script: str, numkeys: int, args: tuple[str, ...]) -> object:
        if "local grant =" in script:
            self.started.set()
            await self.release.wait()
        return await self.redis.eval(script, numkeys, *args)


async def test_late_redis_command_cannot_write_after_source_reset(
    redis_client: Redis,
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await runtime_redis.open_runtime_writes(redis_client, reserved)
    delayed = DelayedWrite(redis_client)
    monkeypatch.setattr(
        "src.infrastructure.cache.redis.get_redis_cache", AsyncMock(return_value=delayed)
    )
    owner = str(reserved.target.owner_id)
    with run_authority_scope(RunAuthority(reserved)):
        task = asyncio.create_task(
            record_occurrence(owner, "email", local_date=DAY, local_hour=9.5, settings=settings)
        )
    try:
        await asyncio.wait_for(delayed.started.wait(), 10)
        await runtime_redis.close_runtime_writes(redis_client, reserved)
        async with AsyncSession(async_engine) as db:
            assert await ConversationExecutionRepository(db).close_owned(
                reserved, end=RunEnd.NORMAL
            )
            await db.commit()
            await ConversationLifecycle(db).request_reset(
                reserved.target.owner_id,
                reserved.target.id,
                operation_id=uuid4(),
                expected_revision=reserved.target.revision,
            )
        delayed.release.set()
        await task
        assert await redis_client.get(recurrence_store.redis_key(owner, "email")) is None
    finally:
        delayed.release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_valid_learning_uses_the_account_key_outside_runtime_cleanup_inventory(
    redis_client: Redis, reserved: RunAdmission, monkeypatch: pytest.MonkeyPatch
) -> None:
    await runtime_redis.open_runtime_writes(redis_client, reserved)
    monkeypatch.setattr(
        "src.infrastructure.cache.redis.get_redis_cache", AsyncMock(return_value=redis_client)
    )
    owner = str(reserved.target.owner_id)
    with run_authority_scope(RunAuthority(reserved)):
        await record_occurrence(
            owner, "email", local_date=DAY, local_hour=9.5, settings=settings, intent="search"
        )
    key = recurrence_store.redis_key(owner, "email")
    data = await recurrence_store.load(redis_client, key)
    assert data["days"] == {DAY.isoformat(): [9.5]}
    assert data["intents"] == {"search": 1}
    assert await redis_client.ttl(key) > 0
    assert not await redis_client.sismember(
        runtime_redis.runtime_inventory_key(reserved.target), key
    )


@pytest.mark.parametrize("withdrawal", ["forget", "disable"])
async def test_withdrawal_fences_a_command_already_waiting_on_redis(
    redis_client: Redis,
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
    withdrawal: str,
) -> None:
    await runtime_redis.open_runtime_writes(redis_client, reserved)
    delayed = DelayedWrite(redis_client)
    monkeypatch.setattr(
        "src.infrastructure.cache.redis.get_redis_cache", AsyncMock(return_value=delayed)
    )
    owner = str(reserved.target.owner_id)
    with run_authority_scope(RunAuthority(reserved)):
        task = asyncio.create_task(
            record_occurrence(owner, "email", local_date=DAY, local_hour=9.5, settings=settings)
        )
    try:
        await asyncio.wait_for(delayed.started.wait(), 10)
        monkeypatch.setattr(
            "src.infrastructure.cache.redis.get_redis_cache", AsyncMock(return_value=redis_client)
        )
        if withdrawal == "forget":
            assert await clear_habit_advisory_state(reserved.target.owner_id)
        else:
            monkeypatch.setattr(
                "src.domains.habits.preference_commands.get_redis_cache",
                AsyncMock(return_value=redis_client),
            )
            async with AsyncSession(async_engine, expire_on_commit=False) as db:
                await update_habit_settings(
                    db, reserved.target.owner_id, HabitsSettingsUpdate(habits_enabled=False)
                )
        delayed.release.set()
        await task
        assert await redis_client.get(recurrence_store.redis_key(owner, "email")) is None
    finally:
        delayed.release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_an_old_seed_cannot_restore_forgotten_learning(redis_client: Redis) -> None:
    owner = str(uuid4())
    token = await recurrence_store.acquire_write_token(redis_client, owner)
    await recurrence_store.delete_user_ledger(redis_client, owner)
    key = recurrence_store.redis_key(owner, "email")
    data = {"days": {DAY.isoformat(): [9.5]}, "origin": recurrence_store.ORIGIN_SEED}
    assert not await recurrence_store.store_if_absent(
        redis_client, key, data, settings.recurrence_window_days, user_id=owner, write_token=token
    )
    assert await redis_client.get(key) is None
    fresh = await recurrence_store.acquire_write_token(redis_client, owner)
    assert await recurrence_store.store_if_absent(
        redis_client, key, data, settings.recurrence_window_days, user_id=owner, write_token=fresh
    )
    assert not await recurrence_store.store_if_absent(
        redis_client, key, data, settings.recurrence_window_days, user_id=owner, write_token=fresh
    )


async def test_retry_of_disabled_preference_finishes_the_failed_revocation(
    redis_client: Redis,
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = reserved.target.owner_id
    token = await recurrence_store.acquire_write_token(redis_client, str(owner))
    monkeypatch.setattr(
        "src.domains.habits.preference_commands.get_redis_cache",
        AsyncMock(side_effect=ConnectionError("unavailable")),
    )
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        with pytest.raises(HabitSettingsCompletionUnknown):
            await update_habit_settings(db, owner, HabitsSettingsUpdate(habits_enabled=False))
    monkeypatch.setattr(
        "src.domains.habits.preference_commands.get_redis_cache",
        AsyncMock(return_value=redis_client),
    )
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        user = await update_habit_settings(db, owner, HabitsSettingsUpdate(habits_enabled=False))
        assert user.extraction_revision == 1
    assert await recurrence_store.acquire_write_token(redis_client, str(owner)) != token
