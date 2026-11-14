"""Real Redis writes require a current SQL owner and an atomically open runtime grant."""

import asyncio
from collections.abc import Awaitable
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.constants import REDIS_KEY_HITL_PENDING_PREFIX
from src.core.conversation_execution import ExecutionRevoked, RunAdmission, RunEnd
from src.core.run_authority import RunAuthority, run_authority_scope
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.infrastructure.streaming import runtime_redis

pytestmark = pytest.mark.integration


def pending_key(admission: RunAdmission) -> str:
    return f"{REDIS_KEY_HITL_PENDING_PREFIX}{admission.target.runtime_id}"


async def put(redis: Redis, admission: RunAdmission, value: str = "question") -> None:
    await runtime_redis.write_runtime_string(
        redis,
        admission.target.runtime_id,
        key=pending_key(admission),
        value=value,
        ttl_seconds=30,
    )


async def test_missing_or_closed_grant_never_creates_pending_state(
    redis_client: Redis,
    reserved: RunAdmission,
) -> None:
    with run_authority_scope(RunAuthority(reserved)):
        with pytest.raises(ExecutionRevoked):
            await put(redis_client, reserved)
        await runtime_redis.open_runtime_writes(redis_client, reserved)
        await put(redis_client, reserved)
        assert await redis_client.get(pending_key(reserved)) is not None
        members = await redis_client.smembers(runtime_redis.runtime_inventory_key(reserved.target))
        assert pending_key(reserved) in {
            member.decode() if isinstance(member, bytes) else member for member in members
        }
        await runtime_redis.close_runtime_writes(redis_client, reserved)
        await redis_client.delete(pending_key(reserved))
        with pytest.raises(ExecutionRevoked):
            await put(redis_client, reserved)
        assert await redis_client.get(pending_key(reserved)) is None


async def test_a_closed_sql_admission_cannot_repair_a_lost_redis_grant(
    redis_client: Redis,
    reserved: RunAdmission,
    async_engine: AsyncEngine,
) -> None:
    await runtime_redis.open_runtime_writes(redis_client, reserved)
    await redis_client.delete(runtime_redis.runtime_writer_key(reserved.target))
    async with AsyncSession(async_engine) as db:
        assert await ConversationExecutionRepository(db).close_owned(reserved, end=RunEnd.NORMAL)
        await db.commit()
    with pytest.raises(ExecutionRevoked):
        await runtime_redis.open_runtime_writes(redis_client, reserved)
    assert (
        await redis_client.hget(runtime_redis.runtime_writer_key(reserved.target), "phase")
        != "active"
    )
    with run_authority_scope(RunAuthority(reserved)), pytest.raises(ExecutionRevoked):
        await put(redis_client, reserved)


class DelayedOpen:
    """Delay only the real opening script, after its actual SQL check."""

    def __init__(self, redis: Redis) -> None:
        self.redis = redis
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    def eval(self, script: str, numkeys: int, /, *args: str) -> Awaitable[object]:
        return self._eval(script, numkeys, args)

    async def _eval(self, script: str, numkeys: int, args: tuple[str, ...]) -> object:
        if script == runtime_redis.OPEN_RUNTIME:
            self.started.set()
            await self.release.wait()
        return await self.redis.eval(script, numkeys, *args)


async def test_an_open_already_in_flight_cannot_reverse_a_close(
    redis_client: Redis,
    reserved: RunAdmission,
) -> None:
    delayed = DelayedOpen(redis_client)
    opening = asyncio.create_task(runtime_redis.open_runtime_writes(delayed, reserved))
    try:
        await delayed.started.wait()
        await runtime_redis.close_runtime_writes(redis_client, reserved)
        delayed.release.set()
        with pytest.raises(ExecutionRevoked):
            await opening
        with run_authority_scope(RunAuthority(reserved)), pytest.raises(ExecutionRevoked):
            await put(redis_client, reserved)
    finally:
        delayed.release.set()
        await asyncio.gather(opening, return_exceptions=True)


async def test_retired_open_request_stays_refused_after_its_tombstone_expires(
    redis_client: Redis,
    reserved: RunAdmission,
) -> None:
    key = runtime_redis.runtime_writer_key(reserved.target)
    # Exercise the server-side expiry check with an already-expired command:
    # no sleeping or host-clock replacement can stand in for Redis TIME.
    now = await runtime_redis.redis_time_ms(redis_client)
    result = await redis_client.eval(
        runtime_redis.OPEN_RUNTIME,
        1,
        key,
        str(reserved.owner_token),
        str(reserved.fence),
        str(now - 1),
        "1000",
    )
    assert result == 0 and not await redis_client.exists(key)


async def test_a_command_cannot_activate_an_expired_ticket_even_with_a_future_deadline(
    redis_client: Redis,
    reserved: RunAdmission,
) -> None:
    key = runtime_redis.runtime_writer_key(reserved.target)
    now = await runtime_redis.redis_time_ms(redis_client)
    # Models a late OPEN after its ticket/closed marker expired, including a
    # backward wall-clock adjustment. A future date alone proves no authority.
    result = await redis_client.eval(
        runtime_redis.OPEN_RUNTIME,
        1,
        key,
        str(reserved.owner_token),
        str(reserved.fence),
        str(now + 1000),
        "1000",
        str(uuid4()),
    )
    assert result == 0 and not await redis_client.exists(key)


async def test_a_writer_cannot_address_another_runtime_or_an_unrelated_key(
    redis_client: Redis,
    reserved: RunAdmission,
) -> None:
    await runtime_redis.open_runtime_writes(redis_client, reserved)
    with run_authority_scope(RunAuthority(reserved)):
        for runtime_id, key in (
            (uuid4(), pending_key(reserved)),
            (reserved.target.runtime_id, f"session:{uuid4()}"),
        ):
            with pytest.raises((ExecutionRevoked, ValueError)):
                await runtime_redis.write_runtime_string(
                    redis_client,
                    runtime_id,
                    key=key,
                    value="private",
                    ttl_seconds=30,
                )
            assert not await redis_client.exists(key)


async def test_cancellation_retires_the_pending_activation_ticket(
    redis_client: Redis,
    reserved: RunAdmission,
) -> None:
    delayed = DelayedOpen(redis_client)
    opening = asyncio.create_task(runtime_redis.open_runtime_writes(delayed, reserved))
    try:
        await delayed.started.wait()
        opening.cancel()
        with pytest.raises(asyncio.CancelledError):
            await opening
        key = runtime_redis.runtime_writer_key(reserved.target)
        assert await redis_client.hget(key, "phase") == "closed"
        assert await redis_client.hget(key, "ticket") is None
    finally:
        delayed.release.set()
        await asyncio.gather(opening, return_exceptions=True)


async def test_expired_real_ticket_cannot_be_replayed(
    redis_client: Redis,
    reserved: RunAdmission,
) -> None:
    key = runtime_redis.runtime_writer_key(reserved.target)
    ticket = str(uuid4())
    deadline = await redis_client.eval(
        runtime_redis.ISSUE_RUNTIME,
        1,
        key,
        str(reserved.owner_token),
        str(reserved.fence),
        "60000",
        ticket,
    )
    assert await redis_client.pexpire(key, 0)
    assert (
        await redis_client.eval(
            runtime_redis.OPEN_RUNTIME,
            1,
            key,
            str(reserved.owner_token),
            str(reserved.fence),
            str(deadline),
            "60000",
            ticket,
        )
        == 0
    )
    assert not await redis_client.exists(key)


async def test_bigint_fences_are_exact_and_stale_closure_cannot_revoke_the_successor(
    redis_client: Redis,
    reserved: RunAdmission,
) -> None:
    key = runtime_redis.runtime_writer_key(reserved.target)
    old_token, new_token = str(uuid4()), str(uuid4())
    old_fence, new_fence = str(2**53), str(2**53 + 1)
    for token, fence in ((old_token, old_fence), (new_token, new_fence)):
        ticket = str(uuid4())
        deadline = await redis_client.eval(
            runtime_redis.ISSUE_RUNTIME,
            1,
            key,
            token,
            fence,
            "60000",
            ticket,
        )
        assert (
            await redis_client.eval(
                runtime_redis.OPEN_RUNTIME,
                1,
                key,
                token,
                fence,
                str(deadline),
                "60000",
                ticket,
            )
            == 1
        )
    assert (
        await redis_client.eval(
            runtime_redis.CLOSE_RUNTIME,
            1,
            key,
            old_token,
            old_fence,
            "60000",
        )
        == 0
    )
    assert (
        await redis_client.eval(
            runtime_redis.ISSUE_RUNTIME,
            1,
            key,
            old_token,
            old_fence,
            "60000",
            str(uuid4()),
        )
        == 0
    )
    assert await redis_client.hget(key, "phase") == "active"
    assert await redis_client.hget(key, "token") == new_token


async def test_wrong_inventory_type_cannot_partially_write_the_question(
    redis_client: Redis,
    reserved: RunAdmission,
) -> None:
    await runtime_redis.open_runtime_writes(redis_client, reserved)
    inventory = runtime_redis.runtime_inventory_key(reserved.target)
    await redis_client.set(inventory, "wrong-type", ex=30)
    with run_authority_scope(RunAuthority(reserved)), pytest.raises(RuntimeError):
        await put(redis_client, reserved)
    assert not await redis_client.exists(pending_key(reserved))
    assert await redis_client.get(inventory) == "wrong-type"
