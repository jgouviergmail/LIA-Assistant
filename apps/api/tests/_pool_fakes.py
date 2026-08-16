"""Shared fake for psycopg ``AsyncConnectionPool`` in fully-mocked factories.

A bare ``AsyncMock()`` pool breaks the LangGraph setup path: the real pool's
``connection()`` is a SYNC call returning an async context manager, and the
setup advisory lock (``src/infrastructure/database/setup_lock.py``) enters
one around ``setup()`` — an AsyncMock's ``connection()`` returns a coroutine
instead and dies on ``async with``. Test doubles must honour the public
contract of what they replace (CLAUDE.md), so both the checkpointer and the
tool-context-store factory suites build their pools here.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock


def fake_psycopg_pool() -> AsyncMock:
    """AsyncMock pool whose ``connection()`` honours the real contract."""
    pool = AsyncMock()

    @asynccontextmanager
    async def _connection() -> AsyncIterator[AsyncMock]:
        yield AsyncMock()

    pool.connection = _connection
    return pool
