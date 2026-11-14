"""Pending questions obey runtime ownership, atomic cleanup and read-only rehydration."""

import asyncio
import json
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from src.core.conversation_execution import ExecutionRevoked, RunAdmission
from src.domains.agents.utils.hitl_store import HITLStore
from src.infrastructure.streaming.run_admission import owned_execution, reserve_execution
from tests.fixtures.persisted_runtimes import persist_runtime_targets

pytestmark = pytest.mark.integration


async def test_only_the_admitted_runtime_can_save_a_question(
    reserved: RunAdmission,
    redis_client: Redis,
) -> None:
    store = HITLStore(redis_client, 30)
    runtime = str(reserved.target.runtime_id)
    payload = {"run_id": reserved.run_id, "action_requests": [{"name": "ask"}]}
    with pytest.raises(ExecutionRevoked):
        await store.save_interrupt(runtime, payload)
    with pytest.raises(ExecutionRevoked):
        await store.delete_interrupt(runtime)
    async with owned_execution(reserved):
        with pytest.raises(ExecutionRevoked):
            await store.save_interrupt(str(uuid4()), payload)
        await store.save_interrupt(runtime, payload)
        pending = await store.get_pending(runtime)
        assert pending is not None and pending["run_id"] == reserved.run_id
    assert await store.get_pending(runtime) is not None
    with pytest.raises(ExecutionRevoked):
        await store.save_interrupt(runtime, payload)


async def test_admitted_cleanup_cannot_delete_another_runtime(
    reserved: RunAdmission,
    redis_client: Redis,
) -> None:
    store = HITLStore(redis_client, 30)
    runtime = str(reserved.target.runtime_id)
    foreign = str(uuid4())
    await redis_client.set(f"hitl_pending:{foreign}", "kept", ex=30)
    async with owned_execution(reserved):
        await store.save_interrupt(runtime, {"run_id": reserved.run_id, "action_requests": []})
        with pytest.raises(ExecutionRevoked):
            await store.clear_interrupt(foreign)
        assert await redis_client.get(f"hitl_pending:{foreign}") == "kept"
        await store.clear_interrupt(runtime)
        assert await store.get_pending(runtime) is None


async def test_reading_legacy_payload_neither_rewrites_nor_extends_its_lifetime(
    reserved: RunAdmission,
    redis_client: Redis,
) -> None:
    runtime = str(reserved.target.runtime_id)
    key = f"hitl_pending:{runtime}"
    raw = json.dumps({"run_id": "old-run", "action_requests": [{"name": "ask"}]})
    await redis_client.set(key, raw, px=8000)
    before = await redis_client.pttl(key)
    assert await HITLStore(redis_client, 3600).get_pending(runtime) is not None
    assert await redis_client.get(key) == raw
    assert 0 < await redis_client.pttl(key) <= before


@pytest.mark.parametrize(
    "raw", ["null", "[]", "true", '"text"', "{", '{"schema_version":1,"interrupt_data":[]}']
)
async def test_malformed_pending_record_is_never_read_as_an_absent_question(
    reserved: RunAdmission,
    redis_client: Redis,
    raw: str,
) -> None:
    runtime = str(reserved.target.runtime_id)
    await redis_client.set(f"hitl_pending:{runtime}", raw, ex=30)
    with pytest.raises(ValueError):
        await HITLStore(redis_client, 30).get_pending(runtime)


async def test_old_cleanup_cannot_remove_a_new_invocation_with_the_same_billing_run(
    reserved: RunAdmission,
    redis_client: Redis,
) -> None:
    runtime = str(reserved.target.runtime_id)
    store = HITLStore(redis_client, 30)
    async with owned_execution(reserved):
        await store.save_interrupt(
            runtime,
            {
                "run_id": reserved.run_id,
                "action_requests": [{"name": "new-question"}],
            },
        )
    assert not await store.clear_interrupt_for_run(runtime, reserved.run_id, activity_id=uuid4())
    assert await store.get_pending(runtime) is not None
    assert await store.clear_interrupt_for_run(
        runtime,
        reserved.run_id,
        activity_id=reserved.activity_id,
    )


async def test_invalid_cleanup_compares_the_exact_record_before_deleting(
    reserved: RunAdmission,
    redis_client: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = str(reserved.target.runtime_id)
    key = f"hitl_pending:{runtime}"
    await redis_client.set(key, json.dumps({"action_requests": []}), ex=30)
    successor = json.dumps({"action_requests": [{"name": "new-question"}]})
    real_get = redis_client.get
    replaced = False

    async def replace_after_read(name: str) -> str | bytes | None:
        nonlocal replaced
        raw = await real_get(name)
        if not replaced:
            replaced = True
            await redis_client.set(key, successor, ex=30)
        return raw

    monkeypatch.setattr(redis_client, "get", replace_after_read)
    assert not await HITLStore(redis_client, 30).clear_if_invalid(runtime)
    assert await real_get(key) == successor


@pytest.mark.asyncio
async def test_hitl_interrupt_stores_pending_state_in_redis(
    reserved: RunAdmission,
    redis_client: Redis,
) -> None:
    store = HITLStore(redis_client, ttl_seconds=300)
    runtime = str(reserved.target.runtime_id)
    data = {"run_id": reserved.run_id, "action_requests": [{"name": "search_contacts_tool"}]}
    async with owned_execution(reserved):
        await store.save_interrupt(runtime, data)
        retrieved = await store.get_interrupt(runtime)
        assert retrieved is not None
        assert retrieved["interrupt_data"] == data
        await store.clear_interrupt(runtime)
        assert await store.get_interrupt(runtime) is None


@pytest.mark.asyncio
async def test_concurrent_hitl_streaming_sessions(
    reserved: RunAdmission,
    redis_client: Redis,
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
) -> None:
    (target,) = await persist_runtime_targets(async_engine, committed_user_ids, count=1)
    second = await reserve_execution(
        target, run_id=str(uuid4()), stream_id=str(uuid4()), relayed=False
    )
    assert isinstance(second, RunAdmission)
    store = HITLStore(redis_client, ttl_seconds=300)
    saved = asyncio.Barrier(2)

    async def publish(admission: RunAdmission, name: str) -> str:
        runtime = str(admission.target.runtime_id)
        async with owned_execution(admission):
            await store.save_interrupt(
                runtime,
                {
                    "run_id": admission.run_id,
                    "action_requests": [{"name": name}],
                },
            )
            await asyncio.wait_for(saved.wait(), 5)
            retrieved = await store.get_pending(runtime)
            assert retrieved is not None
            value = retrieved["action_requests"][0]["name"]
            assert isinstance(value, str)
            await store.clear_interrupt(runtime)
            return value

    assert await asyncio.gather(publish(reserved, "tool_a"), publish(second, "tool_b")) == [
        "tool_a",
        "tool_b",
    ]
