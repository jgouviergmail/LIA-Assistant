"""Integration tests for the pooled LangGraph checkpointer & store (ADR-111).

Runs N concurrent compiled-graph invocations against a REAL PostgreSQL
database through an `AsyncConnectionPool`-backed checkpointer, then verifies
every checkpoint persisted and is resumable. A concurrency property of this
kind cannot be reproduced with mocks: it exercises the pool checkout path,
the pool-aware `_cursor` override and the real checkpoint SQL.

The graph is deliberately trivial (one node incrementing a counter, no LLM):
the subject under test is the persistence layer, not agent logic.

Skipped on Windows for the same reason as tests/unit/test_checkpointer.py
(psycopg v3 async requires SelectorEventLoop); runs in the Linux dev
container and CI.
"""

import asyncio
import sys
from typing import TypedDict, cast
from uuid import uuid4

import pytest
import pytest_asyncio
from langgraph.graph import END, START, StateGraph
from langgraph.store.postgres import AsyncPostgresStore
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from src.domains.conversations.instrumented_checkpointer import (
    InstrumentedAsyncPostgresSaver,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="psycopg v3 async not compatible with Windows ProactorEventLoop in unit tests",
    ),
]

CONCURRENT_INVOCATIONS = 20


def _psycopg_url(test_database_url: str) -> str:
    """Convert the asyncpg test URL to the psycopg3 scheme."""
    return test_database_url.replace("postgresql+asyncpg://", "postgresql://")


def _make_pool(psycopg_url: str, max_size: int) -> AsyncConnectionPool[AsyncConnection[DictRow]]:
    """Build a pool with the exact connection kwargs the factories use."""
    return cast(
        AsyncConnectionPool[AsyncConnection[DictRow]],
        AsyncConnectionPool(
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
        ),
    )


@pytest_asyncio.fixture
async def pooled_saver(test_database_url: str):
    """Pooled instrumented checkpointer against the real test database."""
    pool = _make_pool(_psycopg_url(test_database_url), max_size=8)
    await pool.open(wait=True, timeout=30)
    saver = InstrumentedAsyncPostgresSaver(conn=pool)
    await saver.setup()
    yield saver
    await pool.close()


@pytest_asyncio.fixture
async def pooled_store(test_database_url: str):
    """Pooled AsyncPostgresStore (no semantic index) against the real test DB."""
    pool = _make_pool(_psycopg_url(test_database_url), max_size=4)
    await pool.open(wait=True, timeout=30)
    store = AsyncPostgresStore(conn=pool)
    await store.setup()
    yield store
    await pool.close()


class _CounterState(TypedDict):
    """Minimal graph state: a single integer counter."""

    n: int


def _build_counter_graph(saver: InstrumentedAsyncPostgresSaver):
    """Compile a one-node graph that increments the counter."""

    def bump(state: _CounterState) -> dict[str, int]:
        return {"n": state["n"] + 1}

    builder: StateGraph = StateGraph(_CounterState)
    builder.add_node("bump", bump)
    builder.add_edge(START, "bump")
    builder.add_edge("bump", END)
    return builder.compile(checkpointer=saver)


async def test_concurrent_graph_invocations_checkpoint_correctly(pooled_saver) -> None:
    """N concurrent graph runs must all checkpoint and stay resumable.

    Every invocation uses its own thread_id; results and persisted
    checkpoints must match exactly (no lost/blended state under concurrency).
    """
    graph = _build_counter_graph(pooled_saver)
    thread_ids = [f"pool-concurrency-{uuid4()}" for _ in range(CONCURRENT_INVOCATIONS)]

    try:
        results = await asyncio.gather(
            *[
                graph.ainvoke({"n": i}, config={"configurable": {"thread_id": tid}})
                for i, tid in enumerate(thread_ids)
            ]
        )

        # Every invocation computed its own result
        assert [r["n"] for r in results] == [i + 1 for i in range(CONCURRENT_INVOCATIONS)]

        # Every checkpoint persisted and is resumable (HITL resume relies on this)
        for i, tid in enumerate(thread_ids):
            tup = await pooled_saver.aget_tuple({"configurable": {"thread_id": tid}})
            assert tup is not None, f"missing checkpoint for thread {tid}"
            assert tup.checkpoint["channel_values"]["n"] == i + 1
    finally:
        for tid in thread_ids:
            await pooled_saver.adelete_thread(tid)


async def test_concurrent_store_operations(pooled_store) -> None:
    """N concurrent store put/get cycles must all persist correctly."""
    namespace_root = f"pool-store-test-{uuid4()}"

    async def put_and_read(i: int) -> None:
        namespace = (namespace_root, f"item-{i}")
        await pooled_store.aput(namespace, "key", {"content": f"value-{i}"})
        item = await pooled_store.aget(namespace, "key")
        assert item is not None
        assert item.value == {"content": f"value-{i}"}

    try:
        await asyncio.gather(*[put_and_read(i) for i in range(CONCURRENT_INVOCATIONS)])
    finally:
        for i in range(CONCURRENT_INVOCATIONS):
            await pooled_store.adelete((namespace_root, f"item-{i}"), "key")
