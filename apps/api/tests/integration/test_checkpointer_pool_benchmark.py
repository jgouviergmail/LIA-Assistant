"""Micro-benchmark: single-connection vs pooled LangGraph checkpointer (ADR-111).

Measures the wall-clock time of N concurrent "conversations", each performing
R rounds of checkpoint save (aput) + load (aget_tuple) with a realistic ~4 KB
payload, in two configurations:

- SINGLE: one persistent AsyncConnection (the pre-ADR-111 setup). With a
  non-pool connection the instrumented saver keeps upstream's shared instance
  lock, so every operation of every task serializes.
- POOLED: an AsyncConnectionPool (max_size=8) with the pool-aware `_cursor`
  override, so up to 8 operations run concurrently.

The numbers printed by this test are the before/after evidence quoted in the
ADR-111 pull request. The assertion is deliberately loose (pooled must not be
slower than single + 10% tolerance): micro-benchmarks on shared CI hardware
are noisy, and the goal is to catch a catastrophic regression, not to pin an
exact speedup.

Run manually with:
    pytest tests/integration/test_checkpointer_pool_benchmark.py -v -s
"""

import asyncio
import sys
import time
from copy import deepcopy
from typing import cast
from uuid import uuid4

import pytest
from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata, empty_checkpoint
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from src.domains.conversations.instrumented_checkpointer import (
    InstrumentedAsyncPostgresSaver,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.benchmark,
    pytest.mark.slow,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="psycopg v3 async not compatible with Windows ProactorEventLoop in unit tests",
    ),
]

CONCURRENT_TASKS = 20
ROUNDS_PER_TASK = 5
# Two payload sizes: a small state and a realistic conversation state
# (real MessagesState checkpoints with history routinely reach tens of KB —
# the bigger the payload, the more I/O-bound the operation and the more the
# pool parallelism pays off vs the serialized single connection).
PAYLOAD_SIZES = [4_096, 65_536]
POOL_MAX_SIZE = 8


def _psycopg_url(test_database_url: str) -> str:
    """Convert the asyncpg test URL to the psycopg3 scheme."""
    return test_database_url.replace("postgresql+asyncpg://", "postgresql://")


def _make_checkpoint(
    round_index: int, payload_bytes: int
) -> tuple[Checkpoint, CheckpointMetadata, dict[str, str]]:
    """Build a checkpoint with a ~payload_bytes payload and its new_versions."""
    version = str(round_index + 1)
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {"messages": "x" * payload_bytes}
    checkpoint["channel_versions"] = {"messages": version}
    metadata: CheckpointMetadata = {
        "source": "loop",
        "step": round_index,
        "parents": {},
    }
    return checkpoint, metadata, {"messages": version}


async def _run_workload(
    saver: InstrumentedAsyncPostgresSaver, label: str, payload_bytes: int
) -> float:
    """Run the concurrent aput/aget workload; return elapsed seconds."""
    thread_ids = [f"bench-{label}-{uuid4()}" for _ in range(CONCURRENT_TASKS)]

    async def conversation(tid: str) -> None:
        for r in range(ROUNDS_PER_TASK):
            checkpoint, metadata, new_versions = _make_checkpoint(r, payload_bytes)
            config = {"configurable": {"thread_id": tid, "checkpoint_ns": ""}}
            await saver.aput(config, deepcopy(checkpoint), metadata, new_versions)
            tup = await saver.aget_tuple({"configurable": {"thread_id": tid}})
            assert tup is not None

    started = time.perf_counter()
    try:
        await asyncio.gather(*[conversation(tid) for tid in thread_ids])
        elapsed = time.perf_counter() - started
    finally:
        for tid in thread_ids:
            await saver.adelete_thread(tid)
    return elapsed


@pytest.mark.parametrize("payload_bytes", PAYLOAD_SIZES)
async def test_pooled_checkpointer_beats_single_connection(
    test_database_url: str, payload_bytes: int
) -> None:
    """Before/after benchmark: pooled saver vs the former single connection."""
    url = _psycopg_url(test_database_url)
    conn_kwargs = {"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}

    # --- SINGLE connection (pre-ADR-111 behavior: shared lock serializes) ---
    single_conn = await AsyncConnection.connect(url, **conn_kwargs)
    single_saver = InstrumentedAsyncPostgresSaver(conn=single_conn)
    await single_saver.setup()

    # --- POOLED (ADR-111) ---
    pool = cast(
        AsyncConnectionPool[AsyncConnection[DictRow]],
        AsyncConnectionPool(
            url,
            min_size=1,
            max_size=POOL_MAX_SIZE,
            kwargs=conn_kwargs,
            check=AsyncConnectionPool.check_connection,
            open=False,
        ),
    )
    await pool.open(wait=True, timeout=30)
    pooled_saver = InstrumentedAsyncPostgresSaver(conn=pool)

    try:
        # Warm up both paths (connection caches, table stats) before timing
        await _run_workload(single_saver, "warmup-single", payload_bytes)
        await _run_workload(pooled_saver, "warmup-pooled", payload_bytes)

        single_elapsed = await _run_workload(single_saver, "single", payload_bytes)
        pooled_elapsed = await _run_workload(pooled_saver, "pooled", payload_bytes)
    finally:
        await single_conn.close()
        await pool.close()

    total_ops = CONCURRENT_TASKS * ROUNDS_PER_TASK * 2  # aput + aget per round
    speedup = single_elapsed / pooled_elapsed if pooled_elapsed > 0 else float("inf")
    print(
        f"\n[ADR-111 benchmark] {CONCURRENT_TASKS} concurrent tasks x "
        f"{ROUNDS_PER_TASK} rounds ({total_ops} checkpoint ops, "
        f"{payload_bytes}B payload)\n"
        f"  single connection : {single_elapsed:.3f}s\n"
        f"  pooled (max={POOL_MAX_SIZE})    : {pooled_elapsed:.3f}s\n"
        f"  speedup           : x{speedup:.2f}"
    )

    # Loose guard: the pool must never make things materially worse.
    assert pooled_elapsed <= single_elapsed * 1.10, (
        f"Pooled checkpointer slower than single connection: "
        f"{pooled_elapsed:.3f}s vs {single_elapsed:.3f}s"
    )
