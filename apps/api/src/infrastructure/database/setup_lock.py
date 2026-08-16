"""Serialize LangGraph schema setup across uvicorn workers.

LangGraph's ``AsyncPostgresSaver.setup()`` and ``AsyncPostgresStore.setup()``
run their migrations with no concurrency guard. N workers booting on a
FRESH database race in the PostgreSQL catalog, and the losers die with
``UniqueViolation: duplicate key value violates unique constraint
"pg_type_typname_nsp_index"`` — measured 2026-08-15 on the demonstrator,
whose tmpfs database makes every boot a fresh one: the API stayed in an
import/respawn loop and never served. Production only dodges the race
because its schema was created long ago.

A session-level advisory lock serializes the DDL: one worker wins, the
others retry ``setup()`` AFTER the winner, where it is idempotent.

The waiters POLL ``pg_advisory_try_lock`` — they must never block inside
``pg_advisory_lock``. A blocked SELECT is an active statement holding a
snapshot, and the migrations include ``CREATE INDEX CONCURRENTLY``, which
waits for every snapshot-holding transaction before it can finish: the
holder waits on CIC, CIC waits on the blocked waiters, the waiters wait on
the holder — a live three-way deadlock, measured 2026-08-16 on the
demonstrator (three pids wedged in ``pg_locks``, boot never completing).
Each poll is an instant statement on an autocommit connection, so nothing
lingers for CIC to wait on. The lock is explicitly released in ``finally``:
pool connections are reused, never closed, so a session lock would
otherwise outlive the block.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

#: Distinct advisory keys per schema owner — two subsystems setting up
#: concurrently must not serialize against each other, only against
#: themselves. Arbitrary but stable 64-bit values, namespaced far away from
#: small integers other tooling might pick.
CHECKPOINTER_SETUP_LOCK_KEY = 0x4C49_4143_4B50_0001
TOOL_CONTEXT_STORE_SETUP_LOCK_KEY = 0x4C49_4143_4B50_0002

#: Poll cadence while another worker runs the setup. Setup is seconds on an
#: established schema and tens of seconds on a fresh one; half a second
#: keeps the losers cheap without adding meaningful boot latency.
_TRY_LOCK_POLL_SECONDS = 0.5


@asynccontextmanager
async def postgres_setup_lock(
    pool: Any,
    key: int,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> AsyncIterator[None]:
    """Hold a PostgreSQL session advisory lock around a schema setup.

    Args:
        pool: A psycopg ``AsyncConnectionPool`` (duck-typed: only
            ``connection()`` is used). The lock lives on its own pooled
            connection; the guarded ``setup()`` is free to use others —
            serialization comes from every worker contending on the same key.
        key: 64-bit advisory lock key identifying the schema being set up.
        sleep: Await-between-polls hook, injectable so tests never wait.

    Yields:
        None once the lock is held; releases it on exit, success or failure.
    """
    async with pool.connection() as conn:
        while True:
            # pg_try_advisory_lock — validated against a live PostgreSQL 16
            # (the name is easy to misremember as pg_advisory_try_lock, which
            # does not exist and crash-looped every worker, 2026-08-16).
            cursor = await conn.execute("SELECT pg_try_advisory_lock(%s)", (key,))
            if _first_value(await cursor.fetchone()):
                break
            await sleep(_TRY_LOCK_POLL_SECONDS)
        try:
            yield
        finally:
            await conn.execute("SELECT pg_advisory_unlock(%s)", (key,))


def _first_value(row: Any) -> Any:
    """First column of a fetched row, whatever the pool's row factory.

    The LangGraph pools ship ``row_factory=dict_row`` (a saver requirement),
    so ``row[0]`` raises KeyError there — measured 2026-08-16 on the
    demonstrator. Tuple rows (default factory) stay supported: the helper is
    duck-typed over any psycopg pool.
    """
    if row is None:
        return None
    if isinstance(row, dict):
        return next(iter(row.values()), None)
    return row[0]
