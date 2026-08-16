"""Advisory-lock serialization of LangGraph schema setup (postgres_setup_lock).

LangGraph's ``AsyncPostgresSaver.setup()`` / ``AsyncPostgresStore.setup()``
run plain CREATE TABLE migrations with no concurrency guard: N uvicorn
workers booting on a FRESH database race in the PostgreSQL catalog and the
losers die with ``UniqueViolation: pg_type_typname_nsp_index`` (measured
2026-08-15 on the demonstrator's tmpfs database — the API stayed in an
import/respawn loop for 25 minutes and never served). The helper serializes
the DDL; losers rerun ``setup()`` AFTER the winner, where it is idempotent.

The waiters must POLL ``pg_try_advisory_lock`` — never block inside
``pg_advisory_lock``. A blocked SELECT is an active statement holding a
snapshot, and LangGraph's migrations include ``CREATE INDEX CONCURRENTLY``,
which waits for every snapshot-holding transaction: holder → CIC → blocked
waiters → holder, a live deadlock (measured 2026-08-16 on the demonstrator:
three pids wedged in ``pg_locks``, boot never completing).

Unit scope: mechanics on a scripted fake pool (try-lock polling, body after
acquisition, unlock on success and failure, key passthrough). The real
pg_advisory semantics are PostgreSQL's own contract.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.infrastructure.database.setup_lock import postgres_setup_lock

pytestmark = pytest.mark.unit


class _FakePool:
    """Scripted pool: ``try_lock_results`` drives successive try-lock answers."""

    def __init__(self, try_lock_results: list[bool] | None = None) -> None:
        self.calls: list[tuple[str, Any]] = []
        self._try_results = list(try_lock_results or [True])
        self.conn = AsyncMock()
        self.conn.execute = AsyncMock(side_effect=self._execute)

    #: Row shape returned by ``fetchone`` — the REAL pools ship
    #: ``row_factory=dict_row`` (a saver requirement), so the default fake
    #: does too; ``row[0]`` on that shape raised KeyError in production
    #: (demonstrator, 2026-08-16). ``tuple`` remains covered by a dedicated
    #: test for pools with the default factory.
    row_shape: str = "dict"

    async def _execute(self, sql: str, params: Any) -> AsyncMock:
        self.calls.append((sql, params))
        cursor = AsyncMock()
        if "pg_try_advisory_lock" in sql:
            result = self._try_results.pop(0) if self._try_results else True
        else:
            result = True
        row = {"pg_try_advisory_lock": result} if self.row_shape == "dict" else (result,)
        cursor.fetchone = AsyncMock(return_value=row)
        return cursor

    @asynccontextmanager
    async def connection(self):
        yield self.conn


async def _no_sleep(_seconds: float) -> None:
    return None


async def test_lock_wraps_the_body_and_unlocks() -> None:
    pool = _FakePool([True])
    order: list[str] = []

    async with postgres_setup_lock(pool, 4242, sleep=_no_sleep):
        order.append("body")
        assert [c for c in pool.calls if "pg_try_advisory_lock(" in c[0]], "lock before body"

    order.append("done")
    sqls = [sql for sql, _ in pool.calls]
    assert any("pg_try_advisory_lock(" in s for s in sqls)
    assert any("pg_advisory_unlock(" in s for s in sqls)
    assert sqls.index(next(s for s in sqls if "pg_advisory_unlock(" in s)) == len(sqls) - 1
    assert order == ["body", "done"]


async def test_waiters_poll_instead_of_blocking() -> None:
    """Three refusals then success: four try-lock statements, one body run.

    Each poll is an INSTANT statement on an autocommit connection — no
    snapshot survives between polls, so a concurrent CREATE INDEX
    CONCURRENTLY never waits on us (the 2026-08-16 deadlock shape).
    """
    pool = _FakePool([False, False, False, True])
    ran: list[str] = []

    async with postgres_setup_lock(pool, 4242, sleep=_no_sleep):
        ran.append("body")

    tries = [sql for sql, _ in pool.calls if "pg_try_advisory_lock(" in sql]
    assert len(tries) == 4
    assert ran == ["body"]


async def test_key_is_passed_to_every_call() -> None:
    pool = _FakePool([False, True])
    async with postgres_setup_lock(pool, 777, sleep=_no_sleep):
        pass
    assert all(params == (777,) for _, params in pool.calls)


async def test_unlock_runs_even_when_the_body_raises() -> None:
    """Pool connections are REUSED, never closed: a session advisory lock
    that is not explicitly released outlives the block and deadlocks the
    next boot's setup."""
    pool = _FakePool([True])

    with pytest.raises(RuntimeError):
        async with postgres_setup_lock(pool, 99, sleep=_no_sleep):
            raise RuntimeError("setup blew up")

    assert any("pg_advisory_unlock(" in sql for sql, _ in pool.calls)


async def test_never_blocking_lock_statement_is_used() -> None:
    """The blocking form must NEVER appear: it is the deadlock, not a style
    choice. Guards against a future 'simplification' back to pg_advisory_lock."""
    pool = _FakePool([True])
    async with postgres_setup_lock(pool, 1, sleep=_no_sleep):
        pass
    assert not any(
        "pg_advisory_lock(" in sql and "try" not in sql for sql, _ in pool.calls
    ), "blocking pg_advisory_lock reintroduced — CIC deadlock (2026-08-16)"


async def test_tuple_row_factory_is_also_accepted() -> None:
    """A pool with the default tuple row factory must work too — the helper
    is duck-typed over any psycopg pool, not only the saver-configured one."""
    pool = _FakePool([False, True])
    pool.row_shape = "tuple"
    ran: list[str] = []

    async with postgres_setup_lock(pool, 5, sleep=_no_sleep):
        ran.append("body")

    assert ran == ["body"]
