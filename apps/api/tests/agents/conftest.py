"""Shared pytest configuration for the agents suite.

Installs the deterministic un-awaited-AsyncMock guard (F028) so a coroutine
leaked by a mock in this suite fails its own test instead of flakily surfacing
on an unrelated one. See ``tests._coroutine_leak_guard`` for the rationale.

Also disposes the global SQLAlchemy engine's pooled connections at the end of
any test that actually opened one (F028, async teardown): pytest-asyncio gives
every test its own event loop, but the module-level engine pool outlives it —
a connection created on test N's loop would later be terminated from test
N+k's (or a closed) loop, surfacing as ``RuntimeError: Event loop is closed``
inside asyncpg's cancellation path and cross-loop Future noise.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest

from tests._coroutine_leak_guard import assert_no_unawaited_asyncmock


@pytest.fixture(autouse=True)
def _fail_on_unawaited_asyncmock() -> Iterator[None]:
    """Fail the test that leaks an un-awaited AsyncMock coroutine (F028)."""
    yield from assert_no_unawaited_asyncmock()


@pytest.fixture(autouse=True)
async def _dispose_pooled_db_connections() -> AsyncIterator[None]:
    """Close the global engine's pooled connections on their OWN event loop.

    No-op (a couple of integer reads) for the vast majority of tests that never
    touch the real database; for the few that do, ``engine.dispose()`` closes
    the pooled connections before this test's loop shuts down, so no asyncpg
    connection ever has to be terminated from a foreign/closed loop (F028).
    """
    yield
    from src.infrastructure.database.session import engine

    pool = engine.sync_engine.pool
    checkedin = getattr(pool, "checkedin", lambda: 0)()
    checkedout = getattr(pool, "checkedout", lambda: 0)()
    if checkedin or checkedout:
        await engine.dispose()


@pytest.fixture(autouse=True)
async def _close_global_redis_clients() -> AsyncIterator[None]:
    """Close the global Redis singletons on their OWN event loop (F028, V8).

    Any test that lazily created the module-level Redis clients leaves them
    bound to this test's soon-to-close loop; a client that survives to
    interpreter shutdown is destroyed by the GC on a closed loop, emitting
    ResourceWarning / "Event loop is closed" noise after pytest exits.
    ``close_redis()`` is a no-op when no client was created (the common case)
    and resets the singletons, so the next test lazily rebuilds on ITS loop.
    """
    yield
    from src.infrastructure.cache.redis import close_redis

    await close_redis()


@pytest.fixture(autouse=True)
async def _close_global_psycopg_pools() -> AsyncIterator[None]:
    """Close the psycopg AsyncConnectionPool singletons on their OWN loop (AC-010).

    The checkpointer and the tool-context store each hold a module-level
    ``AsyncConnectionPool`` whose connections wrap asyncio streams. A pool
    created on this test's loop and left to interpreter shutdown is finalized
    by the GC on a closed loop — the "StreamWriter destroyed / unclosed
    Connection" noise the audit saw after the summary. No-op (two attribute
    reads) unless a test actually opened one of the pools.

    Ownership is established by SNAPSHOTTING the singletons before the test: a
    pool that already existed was opened on an EARLIER test's loop, and awaiting
    its workers from here never wakes them (teardown error observed when the
    unit and agents scopes run in one pytest invocation — CI runs them as
    separate invocations, so it only bites locally). Only a pool that appeared
    during this test is ours to close.
    """
    from src.domains.agents.context import store as _context_store
    from src.domains.conversations import checkpointer as _checkpointer

    pool_before = _checkpointer._pool
    store_pool_before = _context_store._store_pool

    yield

    if _checkpointer._pool is not None and _checkpointer._pool is not pool_before:
        await _checkpointer.cleanup_checkpointer()
    if (
        _context_store._store_pool is not None
        and _context_store._store_pool is not store_pool_before
    ):
        await _context_store.cleanup_tool_context_store()


@pytest.fixture(autouse=True)
def _finalize_on_live_loop() -> Iterator[None]:
    """Force GC finalization while this test's loop is still open (AC-010).

    Without this, an object dropped by test N is often collected during test
    N+k (or at interpreter shutdown) — its ResourceWarning then fires on a
    foreign/closed loop and is attributed non-deterministically. Collecting at
    teardown pins every finalizer to the test that leaked, which is what makes
    the teardown-hygiene guard (test_teardown_hygiene_guard.py) deterministic.
    """
    yield
    import gc

    gc.collect()
