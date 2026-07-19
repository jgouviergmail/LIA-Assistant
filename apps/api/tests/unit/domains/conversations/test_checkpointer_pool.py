"""
Unit tests for the pooled LangGraph checkpointer factory (ADR-111).

Covers:
- Pool construction from settings (sizes, connection kwargs, fail-fast open)
- Singleton behavior, cleanup and reset lifecycle
- The pool-aware `_cursor` override of InstrumentedAsyncPostgresSaver:
  pooled savers must NOT serialize concurrent operations, single-connection
  savers must keep the upstream serialized behavior
- Upstream canary: fails when langgraph fixes issue #7259 so the override
  can be removed (see InstrumentedAsyncPostgresSaver._cursor docstring)

These tests are fully mocked (no PostgreSQL connection is ever opened), so
they run on every platform including the Windows host used by pre-commit.
"""

import asyncio
import inspect
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore
from psycopg_pool import AsyncConnectionPool

from src.domains.conversations.checkpointer import (
    cleanup_checkpointer,
    get_checkpointer,
    reset_checkpointer,
)
from src.domains.conversations.instrumented_checkpointer import (
    InstrumentedAsyncPostgresSaver,
)


class TestGetCheckpointerPoolFactory:
    """Tests for get_checkpointer() building an AsyncConnectionPool."""

    @pytest.mark.asyncio
    async def test_builds_pool_from_settings(self, psycopg_url_from_settings):
        """Pool sizes, connection kwargs and fail-fast open come from settings.

        ``psycopg_url_from_settings`` neutralizes the process-wide URL override
        installed by the DB redirection: it wins over ``settings`` by design, so
        without it this assertion is intermittently handed the Testcontainers URL.
        """
        reset_checkpointer()

        with (
            patch("src.domains.conversations.checkpointer.AsyncConnectionPool") as mock_pool_cls,
            patch(
                "src.domains.conversations.checkpointer.InstrumentedAsyncPostgresSaver"
            ) as mock_saver_cls,
            patch("src.domains.conversations.checkpointer.settings") as mock_settings,
            # URL + connection kwargs resolve through the shared helper
            # (src/infrastructure/database/psycopg_pool_config.py) — patch ITS
            # settings so the end-to-end contract stays: settings → pool URL.
            patch("src.infrastructure.database.psycopg_pool_config.settings") as mock_url_settings,
        ):
            mock_url_settings.database_url = "postgresql+asyncpg://user:pass@localhost/db"
            mock_url_settings.database_connect_timeout = 30
            mock_settings.langgraph_checkpoint_pool_min_size = 2
            mock_settings.langgraph_checkpoint_pool_max_size = 7
            mock_settings.database_pool_timeout = 30

            mock_pool = AsyncMock()
            mock_pool_cls.return_value = mock_pool
            mock_saver = AsyncMock()
            mock_saver_cls.return_value = mock_saver

            saver = await get_checkpointer()

            # URL converted to psycopg3 scheme
            assert mock_pool_cls.call_args.args[0] == "postgresql://user:pass@localhost/db"
            # Pool sizes flow from settings (never hardcoded in the factory)
            assert (
                mock_pool_cls.call_args.kwargs["min_size"]
                == mock_settings.langgraph_checkpoint_pool_min_size
            )
            assert (
                mock_pool_cls.call_args.kwargs["max_size"]
                == mock_settings.langgraph_checkpoint_pool_max_size
            )
            # Connection kwargs identical to the former single AsyncConnection
            conn_kwargs = mock_pool_cls.call_args.kwargs["kwargs"]
            assert conn_kwargs["autocommit"] is True
            assert conn_kwargs["prepare_threshold"] == 0
            assert "row_factory" in conn_kwargs
            # libpq bound on connection ESTABLISHMENT (anti-wedge on blackholes)
            assert conn_kwargs["connect_timeout"] == mock_url_settings.database_connect_timeout
            # Deferred explicit open (async constructor open is deprecated)
            assert mock_pool_cls.call_args.kwargs["open"] is False
            mock_pool.open.assert_awaited_once_with(
                wait=True, timeout=mock_settings.database_pool_timeout
            )
            # Saver receives the pool, setup runs once
            assert mock_saver_cls.call_args.kwargs["conn"] is mock_pool
            mock_saver.setup.assert_awaited_once()
            assert saver is mock_saver

        reset_checkpointer()

    @pytest.mark.asyncio
    async def test_singleton_returns_same_instance(self):
        """Repeated calls return the same saver without rebuilding the pool."""
        reset_checkpointer()

        with (
            patch("src.domains.conversations.checkpointer.AsyncConnectionPool") as mock_pool_cls,
            patch(
                "src.domains.conversations.checkpointer.InstrumentedAsyncPostgresSaver"
            ) as mock_saver_cls,
            patch("src.domains.conversations.checkpointer.settings") as mock_settings,
        ):
            mock_settings.database_url = "postgresql+asyncpg://user:pass@localhost/db"
            mock_settings.langgraph_checkpoint_pool_min_size = 1
            mock_settings.langgraph_checkpoint_pool_max_size = 8
            mock_settings.database_pool_timeout = 30
            mock_pool_cls.return_value = AsyncMock()
            mock_saver_cls.return_value = AsyncMock()

            saver1 = await get_checkpointer()
            saver2 = await get_checkpointer()

            assert saver1 is saver2
            assert mock_pool_cls.call_count == 1
            assert mock_saver_cls.return_value.setup.await_count == 1

        reset_checkpointer()

    @pytest.mark.asyncio
    async def test_cleanup_closes_pool_and_allows_recreation(self):
        """cleanup_checkpointer() closes the pool; next call rebuilds everything."""
        reset_checkpointer()

        with (
            patch("src.domains.conversations.checkpointer.AsyncConnectionPool") as mock_pool_cls,
            patch(
                "src.domains.conversations.checkpointer.InstrumentedAsyncPostgresSaver"
            ) as mock_saver_cls,
            patch("src.domains.conversations.checkpointer.settings") as mock_settings,
        ):
            mock_settings.database_url = "postgresql+asyncpg://user:pass@localhost/db"
            mock_settings.langgraph_checkpoint_pool_min_size = 1
            mock_settings.langgraph_checkpoint_pool_max_size = 8
            mock_settings.database_pool_timeout = 30
            mock_pool = AsyncMock()
            mock_pool_cls.return_value = mock_pool
            mock_saver_cls.return_value = AsyncMock()

            await get_checkpointer()
            await cleanup_checkpointer()

            mock_pool.close.assert_awaited_once()

            await get_checkpointer()
            assert mock_pool_cls.call_count == 2

        reset_checkpointer()

    @pytest.mark.asyncio
    async def test_setup_failure_closes_pool_and_allows_retry(self):
        """A setup() failure must not leak the opened pool nor poison the singleton."""
        reset_checkpointer()

        with (
            patch("src.domains.conversations.checkpointer.AsyncConnectionPool") as mock_pool_cls,
            patch(
                "src.domains.conversations.checkpointer.InstrumentedAsyncPostgresSaver"
            ) as mock_saver_cls,
            patch("src.domains.conversations.checkpointer.settings") as mock_settings,
        ):
            mock_settings.database_url = "postgresql+asyncpg://user:pass@localhost/db"
            mock_settings.langgraph_checkpoint_pool_min_size = 1
            mock_settings.langgraph_checkpoint_pool_max_size = 8
            mock_settings.database_pool_timeout = 30

            failing_pool = AsyncMock()
            healthy_pool = AsyncMock()
            mock_pool_cls.side_effect = [failing_pool, healthy_pool]

            failing_saver = AsyncMock()
            failing_saver.setup.side_effect = RuntimeError("setup boom")
            healthy_saver = AsyncMock()
            mock_saver_cls.side_effect = [failing_saver, healthy_saver]

            with pytest.raises(RuntimeError, match="setup boom"):
                await get_checkpointer()
            failing_pool.close.assert_awaited_once()

            saver = await get_checkpointer()
            assert saver is healthy_saver

        reset_checkpointer()

    @pytest.mark.asyncio
    async def test_reset_schedules_pool_close(self):
        """reset_checkpointer() closes the previous pool best-effort via a task."""
        reset_checkpointer()

        with (
            patch("src.domains.conversations.checkpointer.AsyncConnectionPool") as mock_pool_cls,
            patch(
                "src.domains.conversations.checkpointer.InstrumentedAsyncPostgresSaver"
            ) as mock_saver_cls,
            patch("src.domains.conversations.checkpointer.settings") as mock_settings,
        ):
            mock_settings.database_url = "postgresql+asyncpg://user:pass@localhost/db"
            mock_settings.langgraph_checkpoint_pool_min_size = 1
            mock_settings.langgraph_checkpoint_pool_max_size = 8
            mock_settings.database_pool_timeout = 30
            mock_pool = AsyncMock()
            mock_pool_cls.return_value = mock_pool
            mock_saver_cls.return_value = AsyncMock()

            await get_checkpointer()
            reset_checkpointer()
            # Yield to the loop so the scheduled close task runs
            await asyncio.sleep(0)

            mock_pool.close.assert_awaited_once()


class _FakeCursorCM:
    """Async context manager yielding a fake cursor (no database involved)."""

    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *exc_info: object) -> None:
        return None


class _FakeConn:
    """Fake psycopg connection exposing only what _cursor() uses."""

    def cursor(self, *args: Any, **kwargs: Any) -> _FakeCursorCM:
        return _FakeCursorCM()


@asynccontextmanager
async def _fake_get_connection(conn: object) -> AsyncIterator[_FakeConn]:
    """Stand-in for _ainternal.get_connection: never touches the network."""
    yield _FakeConn()


class TestCursorOverrideConcurrency:
    """Behavioral tests for the pool-aware _cursor override."""

    @pytest.mark.asyncio
    async def test_pooled_saver_cursors_run_concurrently(self, monkeypatch):
        """With an AsyncConnectionPool, two _cursor() contexts must overlap.

        Under the upstream (non-overridden) behavior the second _cursor() would
        block on the instance lock until the first one exits, and this test
        would fail with TimeoutError.
        """
        import langgraph.checkpoint.postgres._ainternal as lg_ainternal

        monkeypatch.setattr(lg_ainternal, "get_connection", _fake_get_connection)

        pool = AsyncConnectionPool(
            "postgresql://user:pass@localhost:5432/db",
            open=False,
            min_size=1,
            max_size=2,
        )
        try:
            saver = InstrumentedAsyncPostgresSaver(conn=pool)  # type: ignore[arg-type]

            first_entered = asyncio.Event()
            release_first = asyncio.Event()

            async def hold_cursor() -> None:
                async with saver._cursor():
                    first_entered.set()
                    await release_first.wait()

            async def probe_cursor() -> None:
                await first_entered.wait()
                # Must succeed while the first cursor is still open
                async with asyncio.timeout(2):
                    async with saver._cursor():
                        pass
                release_first.set()

            await asyncio.gather(hold_cursor(), probe_cursor())
        finally:
            await pool.close()

    @pytest.mark.asyncio
    async def test_single_connection_saver_stays_serialized(self, monkeypatch):
        """With a single connection, the upstream serialized behavior is kept."""
        import langgraph.checkpoint.postgres._ainternal as lg_ainternal

        monkeypatch.setattr(lg_ainternal, "get_connection", _fake_get_connection)

        # Any non-pool conn object keeps the shared instance lock
        saver = InstrumentedAsyncPostgresSaver(conn=object())  # type: ignore[arg-type]

        first_entered = asyncio.Event()
        release_first = asyncio.Event()

        async def hold_cursor() -> None:
            async with saver._cursor():
                first_entered.set()
                await release_first.wait()

        async def probe_cursor() -> None:
            await first_entered.wait()

            async def enter() -> None:
                async with saver._cursor():
                    pass

            probe_task = asyncio.create_task(enter())
            await asyncio.sleep(0.05)
            # Still blocked on the shared lock while the first cursor is open
            assert not probe_task.done()
            release_first.set()
            async with asyncio.timeout(2):
                await probe_task

        await asyncio.gather(hold_cursor(), probe_cursor())


class TestUpstreamCanary:
    """Guards that tie the _cursor override to the upstream implementation."""

    def test_override_is_registered(self):
        """The subclass must actually override _cursor (not inherit it)."""
        assert "_cursor" in InstrumentedAsyncPostgresSaver.__dict__

    def test_upstream_cursor_still_locks_pools(self):
        """CANARY: upstream AsyncPostgresSaver._cursor still holds self.lock.

        When this assertion fails, langgraph has fixed
        https://github.com/langchain-ai/langgraph/issues/7259 — REMOVE the
        `_cursor` override in InstrumentedAsyncPostgresSaver, this canary, and
        the pool-aware note in ADR-111.
        """
        source = inspect.getsource(AsyncPostgresSaver._cursor)
        assert "async with self.lock" in source, (
            "Upstream AsyncPostgresSaver._cursor no longer unconditionally "
            "acquires self.lock: issue #7259 looks fixed. Remove the _cursor "
            "override in InstrumentedAsyncPostgresSaver (ADR-111)."
        )

    def test_store_cursor_pattern_still_pool_aware(self):
        """The store `_cursor` (our reference pattern) must stay pool-aware.

        If this fails after a langgraph bump, re-audit the override in
        InstrumentedAsyncPostgresSaver against the new store implementation.
        """
        source = inspect.getsource(AsyncPostgresStore._cursor)
        assert "AsyncConnectionPool" in source, (
            "AsyncPostgresStore._cursor no longer special-cases pools; "
            "re-audit InstrumentedAsyncPostgresSaver._cursor (ADR-111)."
        )
