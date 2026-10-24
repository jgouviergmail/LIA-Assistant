"""The application engine's PostgreSQL bounds, on a real server (audit AC-028, ADR-304).

What the bounds do is a property of the server and the driver together, so it is
proven here, not mocked: a lock wait refused within its bound, a transaction left idle
ended and the pool serving again, a transaction's own bound taking precedence (the
OAuth refresh door relies on it), and the application engine starting every connection
with both.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from prometheus_client import REGISTRY
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.config import settings
from src.infrastructure.database.server_bounds import engine_server_settings, install_bound_counter
from src.infrastructure.database.session import get_db_context

pytestmark = pytest.mark.integration

#: Short enough to keep the suite fast, long enough to be a real wait.
_LOCK_BOUND_MS = 300
_IDLE_BOUND_MS = 500

#: How long past a bound the server may take to say so.
_SLACK_SECONDS = 5.0


def _reached(bound: str) -> float:
    """How many times the engine counted ``bound`` (a series that never fired reads 0)."""
    return REGISTRY.get_sample_value("db_bound_reached_total", {"bound": bound}) or 0.0


@pytest_asyncio.fixture
async def bounded(
    test_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncEngine]:
    """An engine built as the application's is, with bounds short enough to watch."""
    monkeypatch.setattr(settings, "database_lock_timeout_ms", _LOCK_BOUND_MS)
    monkeypatch.setattr(settings, "database_idle_in_transaction_timeout_ms", _IDLE_BOUND_MS)
    engine = create_async_engine(
        test_database_url,
        connect_args={"server_settings": engine_server_settings(), "timeout": 30},
        pool_size=1,
        max_overflow=0,
        pool_pre_ping=True,
    )
    install_bound_counter(engine)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def unbounded(test_database_url: str) -> AsyncIterator[AsyncEngine]:
    """The other party of a lock: a plain connection, as a migration would hold one."""
    engine = create_async_engine(
        test_database_url, poolclass=NullPool, connect_args={"timeout": 30}
    )
    yield engine
    await engine.dispose()


async def test_the_engine_behind_the_sessions_starts_every_connection_bounded() -> None:
    """``get_db_context`` — whose engine the integration suite mirrors — opens bounded."""
    async with get_db_context() as db:
        rows = await db.execute(
            text(
                "SELECT name, setting FROM pg_settings "
                "WHERE name IN ('lock_timeout', 'idle_in_transaction_session_timeout')"
            )
        )
        found = dict(rows.tuples().all())

    assert found == {
        "lock_timeout": str(settings.database_lock_timeout_ms),
        "idle_in_transaction_session_timeout": str(
            settings.database_idle_in_transaction_timeout_ms
        ),
    }


async def test_a_lock_held_elsewhere_is_refused_within_the_bound_and_counted(
    bounded: AsyncEngine, unbounded: AsyncEngine
) -> None:
    key = random.randrange(1, 2**31)
    before = _reached("lock_timeout")
    async with unbounded.connect() as holder:
        await holder.execute(text("SELECT pg_advisory_lock(:key)"), {"key": key})
        try:
            started = time.monotonic()
            with pytest.raises(DBAPIError):
                async with bounded.connect() as waiter:
                    await asyncio.wait_for(
                        waiter.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key}),
                        _LOCK_BOUND_MS / 1000 + _SLACK_SECONDS,
                    )
            waited = time.monotonic() - started
        finally:
            await holder.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})

    assert waited < _LOCK_BOUND_MS / 1000 + _SLACK_SECONDS
    assert _reached("lock_timeout") == before + 1


async def test_an_idle_transaction_is_ended_counted_and_the_pool_serves_again(
    bounded: AsyncEngine,
) -> None:
    """The server ends the session; asyncpg says only « disconnected » — the span counts.

    Through a session, as ``get_db_context`` holds one: a failure is rolled back there.
    """
    sessions = async_sessionmaker(bounded, expire_on_commit=False)
    before = _reached("idle_in_transaction_timeout")
    with pytest.raises(DBAPIError):
        async with sessions() as idle:
            try:
                await idle.execute(text("SELECT 1"))
                await asyncio.sleep(_IDLE_BOUND_MS / 1000 * 3)
                await idle.execute(text("SELECT 1"))
            except Exception:
                await idle.rollback()
                raise

    async with sessions() as again:
        served = (await again.execute(text("SELECT 1"))).scalar_one()

    assert served == 1
    assert _reached("idle_in_transaction_timeout") == before + 1


async def test_a_transaction_s_own_bound_takes_precedence(
    test_database_url: str, unbounded: AsyncEngine
) -> None:
    """The engine's bound is a default: ``SET LOCAL`` tightens it for one transaction."""
    engine = create_async_engine(
        test_database_url,
        poolclass=NullPool,
        connect_args={"server_settings": {"lock_timeout": "60000"}, "timeout": 30},
    )
    key = random.randrange(1, 2**31)
    try:
        async with unbounded.connect() as holder:
            await holder.execute(text("SELECT pg_advisory_lock(:key)"), {"key": key})
            try:
                started = time.monotonic()
                with pytest.raises(DBAPIError):
                    async with engine.connect() as waiter:
                        await waiter.execute(text("SET LOCAL lock_timeout = 200"))
                        await asyncio.wait_for(
                            waiter.execute(
                                text("SELECT pg_advisory_xact_lock(:key)"), {"key": key}
                            ),
                            _SLACK_SECONDS,
                        )
                waited = time.monotonic() - started
            finally:
                await holder.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
    finally:
        await engine.dispose()

    assert waited < _SLACK_SECONDS
