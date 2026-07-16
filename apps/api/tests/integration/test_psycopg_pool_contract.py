"""Integration contract: minimal psycopg pool lifecycle against the test DB.

The LangGraph checkpointer and Store are backed by psycopg
``AsyncConnectionPool``s — a different driver path than the asyncpg SQLAlchemy
fixtures. This exercises the exact lifecycle those singletons rely on
(open → query → close) with the shared configuration helper, proving that:

- the pool connects to the TEST database (explicit URL injection, not the
  developer database from ``.env.test``),
- ``connect_timeout`` bounds connection establishment, so a stalled TCP
  handshake (e.g. a freshly published container port) degrades into a retry
  or a loud ``PoolTimeout`` instead of waiting on kernel TCP behavior, and
- the pool closes cleanly on the test's own event loop.
"""

from __future__ import annotations

import pytest
from psycopg import AsyncConnection
from psycopg.rows import DictRow
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.engine.url import make_url

from src.core.config import settings
from src.infrastructure.database.psycopg_pool_config import (
    psycopg_pool_kwargs,
    resolve_psycopg_url,
)

pytestmark = pytest.mark.integration


async def test_psycopg_pool_open_query_close_on_test_db(test_database_url: str) -> None:
    """Open → SELECT → close, on the injected test-database URL."""
    url = resolve_psycopg_url()
    expected = make_url(test_database_url)
    actual = make_url(url)
    assert (actual.host, actual.port, actual.database) == (
        expected.host,
        expected.port,
        expected.database,
    ), f"psycopg pool URL {actual} does not target the test DB {expected}"

    pool: AsyncConnectionPool[AsyncConnection[DictRow]] = AsyncConnectionPool(
        url,
        min_size=1,
        max_size=2,
        kwargs=psycopg_pool_kwargs(),
        open=False,
    )
    await pool.open(wait=True, timeout=settings.database_pool_timeout)
    try:
        async with pool.connection() as conn:
            cursor = await conn.execute("SELECT current_database() AS db")
            row = await cursor.fetchone()
        assert row is not None
        assert row["db"] == expected.database
    finally:
        await pool.close()
