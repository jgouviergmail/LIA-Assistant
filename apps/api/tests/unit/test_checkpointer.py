"""
Unit tests for LangGraph PostgreSQL Checkpointer.

Tests checkpointer initialization, connection management, and state persistence.

Note: These tests require PostgreSQL connection (psycopg v3) which is incompatible
with Windows ProactorEventLoop. They are skipped on Windows in unit test runs.
They also skip when the database URL resolved by the test settings is
unreachable (the dev container has no PostgreSQL on the .env.test localhost
URL — same guard as conftest._skip_if_db_unreachable; they run in CI).
For integration testing, run: pytest tests/integration/test_checkpointer.py
"""

import socket
import sys
from urllib.parse import urlparse

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from src.core.config import settings
from src.domains.conversations.checkpointer import (
    get_checkpointer,
    reset_checkpointer,
)


def _test_db_reachable() -> bool:
    """True when the database URL from test settings accepts TCP connections."""
    parsed = urlparse(str(settings.database_url).replace("postgresql+asyncpg://", "postgresql://"))
    host, port = parsed.hostname or "localhost", parsed.port or 5432
    try:
        sock = socket.create_connection((host, port), timeout=1)
        sock.close()
        return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    sys.platform != "win32" and not _test_db_reachable(),
    reason="Test database unreachable (no PostgreSQL on the .env.test URL; runs in CI)",
)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="psycopg v3 async not compatible with Windows ProactorEventLoop in unit tests",
)
async def test_get_checkpointer_creates_instance():
    """Test get_checkpointer creates checkpointer instance."""
    # Reset first to ensure clean state
    reset_checkpointer()

    checkpointer = await get_checkpointer()

    assert checkpointer is not None
    assert isinstance(checkpointer, AsyncPostgresSaver)


@pytest.mark.asyncio
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="psycopg v3 async not compatible with Windows ProactorEventLoop in unit tests",
)
@pytest.mark.integration
async def test_get_checkpointer_returns_singleton():
    """Test get_checkpointer returns same instance (singleton pattern)."""
    reset_checkpointer()

    checkpointer1 = await get_checkpointer()
    checkpointer2 = await get_checkpointer()

    # Should be same instance
    assert checkpointer1 is checkpointer2


@pytest.mark.asyncio
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="psycopg v3 async not compatible with Windows ProactorEventLoop in unit tests",
)
@pytest.mark.integration
async def test_reset_checkpointer_clears_singleton():
    """Test reset_checkpointer clears global singleton."""
    # Create checkpointer
    checkpointer1 = await get_checkpointer()

    # Reset
    reset_checkpointer()

    # Should create new instance
    checkpointer2 = await get_checkpointer()

    # Different instances after reset
    assert checkpointer1 is not checkpointer2


@pytest.mark.asyncio
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="psycopg v3 async not compatible with Windows ProactorEventLoop in unit tests",
)
@pytest.mark.integration
async def test_checkpointer_setup_is_idempotent():
    """Test checkpointer setup can be called multiple times safely."""
    reset_checkpointer()

    # Call setup multiple times
    checkpointer1 = await get_checkpointer()
    checkpointer2 = await get_checkpointer()
    checkpointer3 = await get_checkpointer()

    # All should be same instance
    assert checkpointer1 is checkpointer2
    assert checkpointer2 is checkpointer3


@pytest.mark.asyncio
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="psycopg v3 async not compatible with Windows ProactorEventLoop in unit tests",
)
@pytest.mark.integration
async def test_checkpointer_connection_string_format():
    """Test checkpointer uses correct psycopg3 connection string format."""
    reset_checkpointer()

    checkpointer = await get_checkpointer()

    # Verify connection is established (connection attribute should exist)
    assert hasattr(checkpointer, "conn")
    assert checkpointer.conn is not None


# Note: Full integration tests for checkpointer state persistence
# are in tests/integration/test_agents.py since they require LangGraph
