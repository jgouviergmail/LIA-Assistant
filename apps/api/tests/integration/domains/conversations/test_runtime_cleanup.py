"""Exact native cleanup never purges another discussion or account learning."""

from dataclasses import replace
from uuid import uuid4

import pytest
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.base import PutOp
from langgraph.store.postgres import AsyncPostgresStore
from psycopg import AsyncConnection
from psycopg.rows import DictRow
from redis.asyncio import Redis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.constants import CONVERSATION_CLEANUP_PAGE_SIZE, REDIS_KEY_HITL_PENDING_PREFIX
from src.core.conversation_execution import RunAdmission, RunEnd
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.instrumented_checkpointer import InstrumentedAsyncPostgresSaver
from src.domains.conversations.models import Conversation
from src.domains.conversations.runtime_store import RuntimeAsyncPostgresStore, close_native_store
from src.infrastructure import account_cleanup_runtime as native_account
from src.infrastructure import conversation_cleanup_runtime as native_cleanup
from src.infrastructure.observability.metrics_key_families import (
    conversation_cleanup_inventory_refusals_total,
    conversation_reset_keys_deleted_total,
)
from src.infrastructure.streaming import runtime_redis
from src.infrastructure.streaming.runtime_cleanup import purge_runtime_inventory

pytestmark = pytest.mark.integration


async def test_account_store_purge_covers_root_and_children_beyond_one_page(
    native_connection: AsyncConnection[DictRow], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Account erasure removes learning too, but never a neighbouring namespace."""
    owner, other = uuid4(), uuid4()
    store = AsyncPostgresStore(native_connection)
    await store.setup()

    async def get_store() -> AsyncPostgresStore:
        return store

    monkeypatch.setattr(native_account, "get_tool_context_store", get_store)
    namespaces = [(str(owner),), (str(owner), "memories")]
    namespaces.extend(
        (str(owner), "context", f"child-{index}")
        for index in range(CONVERSATION_CLEANUP_PAGE_SIZE + 1)
    )
    foreign = (str(other), "memories")
    try:
        await store.abatch([PutOp(ns, "item", {"evidence": True}) for ns in [*namespaces, foreign]])
        adapter = native_account.NativeAccountCleanup()
        assert await adapter.purge_store(owner) == len(namespaces)
        assert await adapter.purge_store(owner) == 0
        assert await store.asearch((str(owner),)) == []
        assert await store.aget(foreign, "item") is not None
    finally:
        await store.abatch([PutOp(ns, "item", None) for ns in [*namespaces, foreign]])
        await close_native_store(store)


async def test_inventory_cleanup_keeps_main_other_annex_and_unrelated_cache(
    redis_client: Redis,
    reserved: RunAdmission,
) -> None:
    target = reserved.target
    main = replace(target, id=target.owner_id, runtime_id=target.owner_id)
    sibling = replace(target, id=uuid4(), runtime_id=uuid4())
    current_key = f"{REDIS_KEY_HITL_PENDING_PREFIX}{target.runtime_id}"
    keep = [
        f"{REDIS_KEY_HITL_PENDING_PREFIX}{main.runtime_id}",
        f"{REDIS_KEY_HITL_PENDING_PREFIX}{sibling.runtime_id}",
        f"briefing:cards:{target.owner_id}",
        f"gmail_history_anchor:{target.owner_id}",
        f"recurrence:{target.owner_id}:email",
        f"debug:jev:{target.owner_id}",
        f"usage_limit:{target.owner_id}",
        f"gmail:search:{target.owner_id}:needle",
        "llm_cache:_call_router_llm:shared",
    ]
    for key in [current_key, *keep]:
        await redis_client.set(key, "evidence", ex=60)
    await redis_client.sadd(runtime_redis.runtime_inventory_key(target), current_key)
    metric = conversation_reset_keys_deleted_total.labels(
        family=REDIS_KEY_HITL_PENDING_PREFIX.rstrip(":")
    )
    before = metric._value.get()
    assert await purge_runtime_inventory(redis_client, target)
    assert metric._value.get() == before + 1
    assert await purge_runtime_inventory(redis_client, target)
    assert metric._value.get() == before + 1
    assert await redis_client.get(current_key) is None
    assert all([await redis_client.get(key) is not None for key in keep])


async def test_unknown_inventory_member_refuses_without_deleting_it(
    redis_client: Redis,
    reserved: RunAdmission,
) -> None:
    target = reserved.target
    foreign = f"{REDIS_KEY_HITL_PENDING_PREFIX}{uuid4()}"
    await redis_client.set(foreign, "keep", ex=60)
    await redis_client.sadd(runtime_redis.runtime_inventory_key(target), foreign)
    before = conversation_cleanup_inventory_refusals_total._value.get()
    assert not await purge_runtime_inventory(redis_client, target)
    assert conversation_cleanup_inventory_refusals_total._value.get() == before + 1
    assert await redis_client.get(foreign) is not None
    assert await redis_client.exists(runtime_redis.runtime_inventory_key(target))


async def test_cleanup_revokes_an_opening_ticket_before_it_can_recreate_runtime_state(
    redis_client: Redis,
    reserved: RunAdmission,
) -> None:
    target = reserved.target
    ticket = str(uuid4())
    deadline = await redis_client.eval(
        runtime_redis.ISSUE_RUNTIME,
        1,
        runtime_redis.runtime_writer_key(target),
        str(reserved.owner_token),
        str(reserved.fence),
        "60000",
        ticket,
    )
    assert await purge_runtime_inventory(redis_client, target)
    result = await redis_client.eval(
        runtime_redis.OPEN_RUNTIME,
        1,
        runtime_redis.runtime_writer_key(target),
        str(reserved.owner_token),
        str(reserved.fence),
        str(deadline),
        "60000",
        ticket,
    )
    assert result == 0


async def test_native_checkpoint_children_and_paged_store_cleanup_keep_other_contexts(
    native_connection: AsyncConnection[DictRow],
    async_engine: AsyncEngine,
    reserved: RunAdmission,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = reserved.target
    raw_saver = AsyncPostgresSaver(native_connection)
    await raw_saver.setup()
    raw_store = AsyncPostgresStore(native_connection)
    store = RuntimeAsyncPostgresStore(native_connection)
    saver = InstrumentedAsyncPostgresSaver(native_connection)
    await store.setup()

    async def get_saver() -> InstrumentedAsyncPostgresSaver:
        return saver

    async def get_store() -> AsyncPostgresStore:
        return store

    monkeypatch.setattr(native_cleanup, "get_checkpointer", get_saver)
    monkeypatch.setattr(native_cleanup, "get_tool_context_store", get_store)
    other_runtime = str(uuid4())
    kept_namespaces = [
        (str(target.owner_id), other_runtime, "context", "email"),
        (str(target.owner_id), "memories"),
        (str(uuid4()), str(target.runtime_id), "context", "email"),
    ]
    prefix = (str(target.owner_id), str(target.runtime_id), "context")
    try:
        for runtime, namespace in (
            (str(target.runtime_id), ""),
            (str(target.runtime_id), "child"),
            (other_runtime, ""),
        ):
            await raw_saver.aput(
                {"configurable": {"thread_id": runtime, "checkpoint_ns": namespace}},
                empty_checkpoint(),
                {"source": "input", "step": 0, "parents": {}},
                {},
            )
        await raw_store.abatch(
            [
                PutOp((*prefix, "email", f"child-{index}"), f"item-{index}", {"kept": False})
                for index in range(CONVERSATION_CLEANUP_PAGE_SIZE + 1)
            ]
            + [PutOp(namespace, "keep", {"kept": True}) for namespace in kept_namespaces]
        )
        async with AsyncSession(async_engine) as db:
            assert await ConversationExecutionRepository(db).close_owned(
                reserved, end=RunEnd.NORMAL
            )
            await db.execute(
                update(Conversation)
                .where(Conversation.id == target.id)
                .values(runtime_id=uuid4(), revision=target.revision + 1)
            )
            await db.commit()
        adapter = native_cleanup.NativeRuntimeCleanup()
        assert await adapter.purge_checkpoint(target)
        assert (
            await raw_saver.aget_tuple({"configurable": {"thread_id": other_runtime}}) is not None
        )
        assert (
            await raw_saver.aget_tuple(
                {"configurable": {"thread_id": str(target.runtime_id), "checkpoint_ns": "child"}}
            )
            is None
        )
        assert await adapter.purge_tool_context(target)
        assert await raw_store.asearch(prefix) == []
        for kept_namespace in kept_namespaces:
            assert await raw_store.aget(kept_namespace, "keep") is not None
    finally:
        await raw_saver.adelete_thread(str(target.runtime_id))
        await raw_saver.adelete_thread(other_runtime)
        await raw_store.abatch(
            [
                PutOp((*prefix, "email", f"child-{index}"), f"item-{index}", None)
                for index in range(CONVERSATION_CLEANUP_PAGE_SIZE + 1)
            ]
            + [PutOp(namespace, "keep", None) for namespace in kept_namespaces]
        )
        await close_native_store(store)
        await close_native_store(raw_store)
