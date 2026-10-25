"""A task cancelled while its session closes, on a real PostgreSQL server.

When a task is cancelled mid-transaction, the session's close is what rolls back
and hands the connection back to the pool: ``CancelledError`` is no
``Exception``, so the helper's rollback branch never runs. A cancellation
re-delivered during that close — what an anyio cancel scope does — must neither
cut the close short (the connection would stay checked out) nor be swallowed
(the task would carry on). Proven with the asyncpg driver and a real pool, which
the unit tests cannot hold.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import QueuePool

from src.infrastructure.database import session as session_module
from src.infrastructure.database.session import get_db_context

pytestmark = pytest.mark.integration


@dataclass
class _Gate:
    """Holds the close of the test's session until the test releases it."""

    started: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass
class _GatedPool:
    engine: AsyncEngine
    gate: _Gate


def _checked_out(engine: AsyncEngine) -> int:
    """Connections the engine's pool has handed out and not taken back."""
    pool = engine.pool
    assert isinstance(pool, QueuePool)
    return pool.checkedout()


@pytest_asyncio.fixture
async def gated_pool(
    test_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[_GatedPool]:
    """A real pooled engine whose sessions run their real close once released."""
    engine = create_async_engine(test_database_url, pool_size=1, max_overflow=0)
    gate = _Gate()

    class _GatedSession(AsyncSession):
        async def close(self) -> None:
            gate.started.set()
            await gate.release.wait()
            await super().close()

    monkeypatch.setattr(
        session_module,
        "AsyncSessionLocal",
        async_sessionmaker(engine, class_=_GatedSession, expire_on_commit=False),
    )
    yield _GatedPool(engine=engine, gate=gate)
    await engine.dispose()


async def test_a_re_delivered_cancellation_returns_the_connection_before_the_task_ends(
    gated_pool: _GatedPool,
) -> None:
    holding = asyncio.Event()

    async def work() -> None:
        async with get_db_context() as db:
            await db.execute(text("SELECT 1"))
            holding.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(work())
    await holding.wait()
    checked_out_at_end: list[int] = []
    task.add_done_callback(lambda _done: checked_out_at_end.append(_checked_out(gated_pool.engine)))

    # Mid-transaction: no rollback ran, the close is what returns the connection.
    task.cancel()
    await gated_pool.gate.started.wait()
    assert _checked_out(gated_pool.engine) == 1

    # Re-delivered while the close runs.
    task.cancel()
    for _ in range(3):
        await asyncio.sleep(0)
    assert not task.done(), "the task ended while its connection was still out"
    gated_pool.gate.release.set()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert checked_out_at_end == [0]
