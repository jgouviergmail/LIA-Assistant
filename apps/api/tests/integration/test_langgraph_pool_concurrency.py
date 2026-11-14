"""Integration tests for the pooled LangGraph checkpointer & store (ADR-111).

Runs N concurrent compiled-graph invocations against a REAL PostgreSQL
database through an `AsyncConnectionPool`-backed checkpointer, then verifies
every checkpoint persisted and is resumable. A concurrency property of this
kind cannot be reproduced with mocks: it exercises the pool checkout path,
the pool-aware `_cursor` override and the real checkpoint SQL.

The graph is deliberately trivial (one node incrementing a counter, no LLM):
the subject under test is the persistence layer, not agent logic.

Note: psycopg v3 async requires a SelectorEventLoop, which the test suite
provides on Windows (``conftest.pytest_asyncio_loop_factories``) — these
tests RUN on Windows against Testcontainers, as well as in the Linux dev
container and CI.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import TypedDict
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.ext.asyncio import AsyncEngine

from src.core.conversation_target import ConversationRef
from src.domains.conversations.instrumented_checkpointer import (
    InstrumentedAsyncPostgresSaver,
)
from src.domains.conversations.runtime_identity import checkpoint_config, checkpoint_identity
from src.domains.conversations.runtime_store import RuntimeAsyncPostgresStore
from tests.fixtures.persisted_runtimes import admitted_runtime, persist_runtime_targets

pytestmark = pytest.mark.integration

CONCURRENT_INVOCATIONS = 20


def _psycopg_url(test_database_url: str) -> str:
    """Convert the asyncpg test URL to the psycopg3 scheme."""
    return test_database_url.replace("postgresql+asyncpg://", "postgresql://")


def _make_pool(psycopg_url: str, max_size: int) -> AsyncConnectionPool[AsyncConnection[DictRow]]:
    """Build a pool with the exact connection kwargs the factories use."""
    return AsyncConnectionPool[AsyncConnection[DictRow]](
        psycopg_url,
        min_size=1,
        max_size=max_size,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
        check=AsyncConnectionPool.check_connection,
        open=False,
    )


@pytest_asyncio.fixture
async def pooled_saver(test_database_url: str) -> AsyncIterator[InstrumentedAsyncPostgresSaver]:
    """Pooled instrumented checkpointer against the real test database."""
    pool = _make_pool(_psycopg_url(test_database_url), max_size=8)
    await pool.open(wait=True, timeout=30)
    saver = InstrumentedAsyncPostgresSaver(conn=pool)
    try:
        await saver.setup()
        yield saver
    finally:
        await pool.close()


@pytest_asyncio.fixture
async def pooled_store(test_database_url: str) -> AsyncIterator[RuntimeAsyncPostgresStore]:
    """Pooled AsyncPostgresStore (no semantic index) against the real test DB."""
    pool = _make_pool(_psycopg_url(test_database_url), max_size=4)
    await pool.open(wait=True, timeout=30)
    store = RuntimeAsyncPostgresStore(conn=pool)
    try:
        await store.setup()
        yield store
    finally:
        await store.aclose()
        await pool.close()


@pytest_asyncio.fixture
async def runtime_targets(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> list[ConversationRef]:
    """Do not bypass the production ownership boundary in a concurrency test."""
    return await persist_runtime_targets(
        async_engine, committed_user_ids, count=CONCURRENT_INVOCATIONS
    )


class _CounterState(TypedDict):
    """Minimal graph state: a single integer counter."""

    n: int


def _build_counter_graph(
    saver: InstrumentedAsyncPostgresSaver,
) -> CompiledStateGraph[_CounterState, None, _CounterState, _CounterState]:
    """Compile a one-node graph that increments the counter."""

    def bump(state: _CounterState) -> dict[str, int]:
        return {"n": state["n"] + 1}

    builder = StateGraph(_CounterState)
    builder.add_node("bump", bump)
    builder.add_edge(START, "bump")
    builder.add_edge("bump", END)
    return builder.compile(checkpointer=saver)


async def test_concurrent_graph_invocations_checkpoint_correctly(
    pooled_saver: InstrumentedAsyncPostgresSaver,
    runtime_targets: list[ConversationRef],
    async_engine: AsyncEngine,
) -> None:
    """N concurrent graph runs must all checkpoint and stay resumable.

    Every invocation uses its own thread_id; results and persisted
    checkpoints must match exactly (no lost/blended state under concurrency).
    """
    graph = _build_counter_graph(pooled_saver)

    async def invoke(i: int, target: ConversationRef) -> _CounterState:
        async with admitted_runtime(async_engine, target):
            result = await graph.ainvoke({"n": i}, config=checkpoint_config(target))
            assert isinstance(result, dict)
            value = result.get("n")
            assert type(value) is int
            return {"n": value}

    try:
        results = await asyncio.gather(
            *[invoke(i, target) for i, target in enumerate(runtime_targets)]
        )

        # Every invocation computed its own result
        assert [r["n"] for r in results] == [i + 1 for i in range(CONCURRENT_INVOCATIONS)]

        # Every checkpoint persisted and is resumable (HITL resume relies on this)
        for i, target in enumerate(runtime_targets):
            tup = await pooled_saver.aget_tuple(checkpoint_config(target))
            assert tup is not None, f"missing checkpoint for runtime {target.runtime_id}"
            assert tup.checkpoint["channel_values"]["n"] == i + 1
            assert checkpoint_identity(tup.config).conversation_id == target.id
    finally:
        for target in runtime_targets:
            await pooled_saver.adelete_thread(str(target.runtime_id))


async def test_concurrent_store_operations(
    pooled_store: RuntimeAsyncPostgresStore,
    runtime_targets: list[ConversationRef],
    async_engine: AsyncEngine,
) -> None:
    """N concurrent store put/get cycles must all persist correctly."""
    namespace_root = f"pool-store-test-{uuid4()}"

    async def put_and_read(i: int) -> None:
        namespace = (namespace_root, f"item-{i}")
        await pooled_store.aput(namespace, "key", {"content": f"value-{i}"})
        item = await pooled_store.aget(namespace, "key")
        assert item is not None
        assert item.value == {"content": f"value-{i}"}
        target = runtime_targets[i]
        context = (str(target.owner_id), str(target.runtime_id), "context", "event")
        async with admitted_runtime(async_engine, target):
            await pooled_store.aput(context, "key", {"items": [i]}, index=False)
        runtime_item = await pooled_store.aget(context, "key")
        assert runtime_item is not None and runtime_item.value == {"items": [i]}

    try:
        await asyncio.gather(*[put_and_read(i) for i in range(CONCURRENT_INVOCATIONS)])
    finally:
        for i in range(CONCURRENT_INVOCATIONS):
            await pooled_store.adelete((namespace_root, f"item-{i}"), "key")
            target = runtime_targets[i]
            await pooled_store.adelete(
                (str(target.owner_id), str(target.runtime_id), "context", "event"), "key"
            )
