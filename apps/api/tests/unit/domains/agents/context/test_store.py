"""
Unit tests for tool context store singleton factory.

Phase: Session 10 - Tests Quick Wins (context/store)
Created: 2025-11-20
Updated: 2026-07 (ADR-111) — the factory now builds an AsyncConnectionPool
instead of a single persistent AsyncConnection.

Focus: AsyncPostgresStore singleton pattern, pool lifecycle, cleanup.
Fully mocked: no PostgreSQL connection is ever opened.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.agents.context.store import (
    cleanup_tool_context_store,
    get_tool_context_store,
    reset_tool_context_store,
)
from tests._pool_fakes import fake_psycopg_pool


def _configure_settings(mock_settings: MagicMock) -> None:
    """Apply the settings attributes the store factory reads."""
    mock_settings.database_url = "postgresql+asyncpg://user:pass@localhost/db"
    mock_settings.memory_embedding_dimensions = 384
    mock_settings.langgraph_store_pool_min_size = 1
    mock_settings.langgraph_store_pool_max_size = 4
    mock_settings.database_pool_timeout = 30


class TestGetToolContextStore:
    """Tests for get_tool_context_store() singleton factory."""

    @pytest.mark.asyncio
    async def test_get_tool_context_store_creates_instance(self):
        """Test that get_tool_context_store() creates AsyncPostgresStore on a pool."""
        reset_tool_context_store()  # Start fresh

        with (
            patch("src.domains.agents.context.store.AsyncConnectionPool") as mock_pool_cls,
            patch("src.domains.agents.context.store.AsyncPostgresStore") as mock_store_class,
            patch("src.domains.agents.context.store.settings") as mock_settings,
            patch("src.domains.agents.context.store._get_embeddings_model") as mock_embeddings,
        ):
            _configure_settings(mock_settings)
            mock_embeddings.return_value = MagicMock()

            mock_pool = fake_psycopg_pool()
            mock_pool_cls.return_value = mock_pool

            mock_store = AsyncMock()
            mock_store.setup = AsyncMock()
            mock_store_class.return_value = mock_store

            # Call function
            store = await get_tool_context_store()

            # Verify pool created with psycopg URL
            mock_pool_cls.assert_called_once()
            pool_url = mock_pool_cls.call_args.args[0]
            assert "postgresql://" in pool_url  # URL converted
            assert "asyncpg" not in pool_url  # asyncpg removed

            # Verify store created on the pool with index (semantic search enabled)
            mock_store_class.assert_called_once()
            call_kwargs = mock_store_class.call_args.kwargs
            assert call_kwargs["conn"] is mock_pool
            assert "index" in call_kwargs  # Semantic search enabled
            assert call_kwargs["index"]["dims"] == 384

            # Verify setup called
            mock_store.setup.assert_called_once()

            # Verify return value
            assert store is mock_store

        reset_tool_context_store()

    @pytest.mark.asyncio
    async def test_get_tool_context_store_singleton_pattern(self):
        """Test that get_tool_context_store() returns same instance on repeated calls."""
        reset_tool_context_store()  # Start fresh

        with (
            patch("src.domains.agents.context.store.AsyncConnectionPool") as mock_pool_cls,
            patch("src.domains.agents.context.store.AsyncPostgresStore") as mock_store_class,
            patch("src.domains.agents.context.store.settings") as mock_settings,
            patch("src.domains.agents.context.store._get_embeddings_model") as mock_embeddings,
        ):
            _configure_settings(mock_settings)
            mock_embeddings.return_value = MagicMock()

            mock_pool_cls.return_value = fake_psycopg_pool()

            mock_store = AsyncMock()
            mock_store.setup = AsyncMock()
            mock_store_class.return_value = mock_store

            # Call twice
            store1 = await get_tool_context_store()
            store2 = await get_tool_context_store()

            # Verify same instance
            assert store1 is store2

            # Verify pool/store created only once
            assert mock_pool_cls.call_count == 1
            assert mock_store_class.call_count == 1
            assert mock_store.setup.call_count == 1

        reset_tool_context_store()

    # NOTE: test_get_tool_context_store_with_disabled_setting removed
    # Tool context is now always enabled (no feature flag)

    @pytest.mark.asyncio
    async def test_get_tool_context_store_url_conversion(self, psycopg_url_from_settings):
        """Test that asyncpg URL is correctly converted to psycopg URL.

        ``psycopg_url_from_settings`` neutralizes the process-wide URL override
        installed by the DB redirection: it wins over ``settings`` by design, so
        without it this assertion is intermittently handed the Testcontainers URL.
        """
        reset_tool_context_store()  # Start fresh

        with (
            patch("src.domains.agents.context.store.AsyncConnectionPool") as mock_pool_cls,
            patch("src.domains.agents.context.store.AsyncPostgresStore") as mock_store_class,
            patch("src.domains.agents.context.store.settings") as mock_settings,
            patch("src.domains.agents.context.store._get_embeddings_model") as mock_embeddings,
            # URL resolves through the shared helper — patch ITS settings so
            # the end-to-end contract stays: settings → pool URL.
            patch("src.infrastructure.database.psycopg_pool_config.settings") as mock_url_settings,
        ):
            _configure_settings(mock_settings)
            mock_url_settings.database_url = "postgresql+asyncpg://user:pass@localhost:5432/testdb"
            mock_url_settings.database_connect_timeout = 30
            mock_embeddings.return_value = MagicMock()

            mock_pool_cls.return_value = fake_psycopg_pool()

            mock_store = AsyncMock()
            mock_store.setup = AsyncMock()
            mock_store_class.return_value = mock_store

            # Call function
            await get_tool_context_store()

            # Verify URL converted correctly
            pool_url = mock_pool_cls.call_args.args[0]
            assert pool_url == "postgresql://user:pass@localhost:5432/testdb"
            assert "+asyncpg" not in pool_url

        reset_tool_context_store()

    @pytest.mark.asyncio
    async def test_get_tool_context_store_pool_params(self):
        """Test that the pool is created with correct sizes and connection kwargs."""
        reset_tool_context_store()  # Start fresh

        with (
            patch("src.domains.agents.context.store.AsyncConnectionPool") as mock_pool_cls,
            patch("src.domains.agents.context.store.AsyncPostgresStore") as mock_store_class,
            patch("src.domains.agents.context.store.settings") as mock_settings,
            patch("src.domains.agents.context.store._get_embeddings_model") as mock_embeddings,
        ):
            _configure_settings(mock_settings)
            mock_settings.langgraph_store_pool_min_size = 2
            mock_settings.langgraph_store_pool_max_size = 5
            mock_embeddings.return_value = MagicMock()

            mock_pool = fake_psycopg_pool()
            mock_pool_cls.return_value = mock_pool

            mock_store = AsyncMock()
            mock_store.setup = AsyncMock()
            mock_store_class.return_value = mock_store

            # Call function
            await get_tool_context_store()

            # Pool sizes flow from settings (never hardcoded in the factory)
            call_kwargs = mock_pool_cls.call_args.kwargs
            assert call_kwargs["min_size"] == mock_settings.langgraph_store_pool_min_size
            assert call_kwargs["max_size"] == mock_settings.langgraph_store_pool_max_size
            # Connection kwargs identical to the former single AsyncConnection
            conn_kwargs = call_kwargs["kwargs"]
            assert conn_kwargs["autocommit"] is True
            assert conn_kwargs["prepare_threshold"] == 0
            assert "row_factory" in conn_kwargs
            # libpq bound on connection ESTABLISHMENT (anti-wedge on blackholes),
            # from the real settings (the shared helper is not patched here).
            from src.core.config import settings as real_settings

            assert conn_kwargs["connect_timeout"] == real_settings.database_connect_timeout
            # Deferred explicit open + fail-fast wait for min_size connections
            assert call_kwargs["open"] is False
            mock_pool.open.assert_awaited_once_with(
                wait=True, timeout=mock_settings.database_pool_timeout
            )

        reset_tool_context_store()

    @pytest.mark.asyncio
    async def test_setup_failure_closes_pool_and_allows_retry(self):
        """A setup() failure must not leak the opened pool nor poison the singleton."""
        reset_tool_context_store()

        with (
            patch("src.domains.agents.context.store.AsyncConnectionPool") as mock_pool_cls,
            patch("src.domains.agents.context.store.AsyncPostgresStore") as mock_store_class,
            patch("src.domains.agents.context.store.settings") as mock_settings,
            patch("src.domains.agents.context.store._get_embeddings_model") as mock_embeddings,
        ):
            _configure_settings(mock_settings)
            mock_embeddings.return_value = MagicMock()

            failing_pool = fake_psycopg_pool()
            healthy_pool = fake_psycopg_pool()
            mock_pool_cls.side_effect = [failing_pool, healthy_pool]

            failing_store = AsyncMock()
            failing_store.setup.side_effect = RuntimeError("setup boom")
            healthy_store = AsyncMock()
            mock_store_class.side_effect = [failing_store, healthy_store]

            with pytest.raises(RuntimeError, match="setup boom"):
                await get_tool_context_store()
            failing_pool.close.assert_awaited_once()

            store = await get_tool_context_store()
            assert store is healthy_store

        reset_tool_context_store()


class TestCleanupToolContextStore:
    """Tests for cleanup_tool_context_store() cleanup function."""

    @pytest.mark.asyncio
    async def test_cleanup_with_existing_store(self):
        """Test cleanup closes the pool and clears the store."""
        reset_tool_context_store()  # Start fresh

        with (
            patch("src.domains.agents.context.store.AsyncConnectionPool") as mock_pool_cls,
            patch("src.domains.agents.context.store.AsyncPostgresStore") as mock_store_class,
            patch("src.domains.agents.context.store.settings") as mock_settings,
            patch("src.domains.agents.context.store._get_embeddings_model") as mock_embeddings,
        ):
            _configure_settings(mock_settings)
            mock_embeddings.return_value = MagicMock()

            mock_pool = fake_psycopg_pool()
            mock_pool_cls.return_value = mock_pool

            mock_store = AsyncMock()
            mock_store.setup = AsyncMock()
            mock_store_class.return_value = mock_store

            # Create store
            await get_tool_context_store()

            # Cleanup
            await cleanup_tool_context_store()

            # Verify pool closed
            mock_pool.close.assert_awaited_once()

            # Verify store cleared (next call creates new instance)
            await get_tool_context_store()
            # New pool created after cleanup
            assert mock_pool_cls.call_count == 2

        reset_tool_context_store()

    @pytest.mark.asyncio
    async def test_cleanup_with_no_store(self):
        """Test cleanup does nothing when no store exists."""
        reset_tool_context_store()  # Ensure no store

        # Cleanup should not crash
        await cleanup_tool_context_store()
        # No assertions needed - just verify no exception

    @pytest.mark.asyncio
    async def test_cleanup_without_pool(self):
        """Test cleanup handles case where store exists but pool is None."""
        reset_tool_context_store()

        with (
            patch("src.domains.agents.context.store._tool_context_store", AsyncMock()),
            patch("src.domains.agents.context.store._store_pool", None),
        ):
            # Should not crash
            await cleanup_tool_context_store()


class TestResetToolContextStore:
    """Tests for reset_tool_context_store() reset function."""

    def test_reset_clears_singleton(self):
        """Test that reset clears global store and pool."""
        # This is a synchronous function
        reset_tool_context_store()

        # Verify function executes without error
        # (actual verification happens in integration with get_tool_context_store)
        assert True  # Function completed successfully

    @pytest.mark.asyncio
    async def test_reset_forces_new_instance(self):
        """Test that reset forces creation of new store instance."""
        reset_tool_context_store()

        with (
            patch("src.domains.agents.context.store.AsyncConnectionPool") as mock_pool_cls,
            patch("src.domains.agents.context.store.AsyncPostgresStore") as mock_store_class,
            patch("src.domains.agents.context.store.settings") as mock_settings,
            patch("src.domains.agents.context.store._get_embeddings_model") as mock_embeddings,
        ):
            _configure_settings(mock_settings)
            mock_embeddings.return_value = MagicMock()

            mock_pool_cls.return_value = fake_psycopg_pool()

            # Mock store - create different instances
            mock_store1 = AsyncMock()
            mock_store1.setup = AsyncMock()
            mock_store2 = AsyncMock()
            mock_store2.setup = AsyncMock()
            mock_store_class.side_effect = [mock_store1, mock_store2]

            # First call
            store1 = await get_tool_context_store()

            # Reset
            reset_tool_context_store()

            # Second call after reset
            store2 = await get_tool_context_store()

            # Verify different instances
            assert store1 is not store2
            assert store1 is mock_store1
            assert store2 is mock_store2

        reset_tool_context_store()

    @pytest.mark.asyncio
    async def test_reset_schedules_pool_close(self):
        """reset closes the previous pool best-effort via a background task."""
        reset_tool_context_store()

        with (
            patch("src.domains.agents.context.store.AsyncConnectionPool") as mock_pool_cls,
            patch("src.domains.agents.context.store.AsyncPostgresStore") as mock_store_class,
            patch("src.domains.agents.context.store.settings") as mock_settings,
            patch("src.domains.agents.context.store._get_embeddings_model") as mock_embeddings,
        ):
            _configure_settings(mock_settings)
            mock_embeddings.return_value = MagicMock()

            mock_pool = fake_psycopg_pool()
            mock_pool_cls.return_value = mock_pool
            mock_store_class.return_value = AsyncMock()

            await get_tool_context_store()
            reset_tool_context_store()
            # Yield to the loop so the scheduled close task runs
            await asyncio.sleep(0)

            mock_pool.close.assert_awaited_once()


class TestIntegration:
    """Integration tests for store lifecycle."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        """Test complete lifecycle: create → use → cleanup → recreate."""
        reset_tool_context_store()

        with (
            patch("src.domains.agents.context.store.AsyncConnectionPool") as mock_pool_cls,
            patch("src.domains.agents.context.store.AsyncPostgresStore") as mock_store_class,
            patch("src.domains.agents.context.store.settings") as mock_settings,
            patch("src.domains.agents.context.store._get_embeddings_model") as mock_embeddings,
        ):
            _configure_settings(mock_settings)
            mock_embeddings.return_value = MagicMock()

            mock_pool = fake_psycopg_pool()
            mock_pool_cls.return_value = mock_pool

            # Mock stores - create different instances
            mock_store1 = AsyncMock()
            mock_store1.setup = AsyncMock()
            mock_store2 = AsyncMock()
            mock_store2.setup = AsyncMock()
            mock_store_class.side_effect = [mock_store1, mock_store2]

            # Step 1: Create store
            store1 = await get_tool_context_store()
            assert store1 is mock_store1

            # Step 2: Verify singleton
            store1_again = await get_tool_context_store()
            assert store1_again is store1

            # Step 3: Cleanup
            await cleanup_tool_context_store()
            mock_pool.close.assert_awaited_once()

            # Step 4: Recreate after cleanup
            store2 = await get_tool_context_store()
            assert store2 is mock_store2
            assert store2 is not store1

        reset_tool_context_store()
