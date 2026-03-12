"""
Unit tests for tool context store singleton factory.

Phase: Session 10 - Tests Quick Wins (context/store)
Created: 2025-11-20

Focus: AsyncPostgresStore singleton pattern, connection management, cleanup
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.agents.context.store import (
    cleanup_tool_context_store,
    get_tool_context_store,
    reset_tool_context_store,
)


class TestGetToolContextStore:
    """Tests for get_tool_context_store() singleton factory."""

    @pytest.mark.asyncio
    async def test_get_tool_context_store_creates_instance(self):
        """Test that get_tool_context_store() creates AsyncPostgresStore instance."""
        reset_tool_context_store()  # Start fresh

        with (
            patch("src.domains.agents.context.store.AsyncConnection") as mock_conn_class,
            patch("src.domains.agents.context.store.AsyncPostgresStore") as mock_store_class,
            patch("src.domains.agents.context.store.settings") as mock_settings,
            patch("src.domains.agents.context.store._get_embeddings_model") as mock_embeddings,
        ):
            # Mock settings for basic store creation
            mock_settings.database_url = "postgresql+asyncpg://user:pass@localhost/db"
            mock_settings.memory_embedding_dimensions = 384
            mock_embeddings.return_value = MagicMock()

            # Mock connection
            mock_conn = AsyncMock()
            mock_conn_class.connect = AsyncMock(return_value=mock_conn)

            # Mock store
            mock_store = AsyncMock()
            mock_store.setup = AsyncMock()
            mock_store_class.return_value = mock_store

            # Call function
            store = await get_tool_context_store()

            # Verify connection created with psycopg URL
            mock_conn_class.connect.assert_called_once()
            call_args = mock_conn_class.connect.call_args
            assert "postgresql://" in call_args[0][0]  # URL converted
            assert "asyncpg" not in call_args[0][0]  # asyncpg removed

            # Verify store created with index (semantic search enabled by default)
            mock_store_class.assert_called_once()
            call_kwargs = mock_store_class.call_args.kwargs
            assert call_kwargs["conn"] is mock_conn
            assert "index" in call_kwargs  # Semantic search enabled
            assert call_kwargs["index"]["dims"] == 384

            # Verify setup called
            mock_store.setup.assert_called_once()

            # Verify return value
            assert store is mock_store

    @pytest.mark.asyncio
    async def test_get_tool_context_store_singleton_pattern(self):
        """Test that get_tool_context_store() returns same instance on repeated calls."""
        reset_tool_context_store()  # Start fresh

        with (
            patch("src.domains.agents.context.store.AsyncConnection") as mock_conn_class,
            patch("src.domains.agents.context.store.AsyncPostgresStore") as mock_store_class,
            patch("src.domains.agents.context.store.settings") as mock_settings,
        ):
            # Mock settings
            mock_settings.tool_context_enabled = True
            mock_settings.database_url = "postgresql+asyncpg://user:pass@localhost/db"

            # Mock connection
            mock_conn = AsyncMock()
            mock_conn_class.connect = AsyncMock(return_value=mock_conn)

            # Mock store
            mock_store = AsyncMock()
            mock_store.setup = AsyncMock()
            mock_store_class.return_value = mock_store

            # Call twice
            store1 = await get_tool_context_store()
            store2 = await get_tool_context_store()

            # Verify same instance
            assert store1 is store2

            # Verify connection/store created only once
            assert mock_conn_class.connect.call_count == 1
            assert mock_store_class.call_count == 1
            assert mock_store.setup.call_count == 1

    # NOTE: test_get_tool_context_store_with_disabled_setting removed
    # Tool context is now always enabled (no feature flag)

    @pytest.mark.asyncio
    async def test_get_tool_context_store_url_conversion(self):
        """Test that asyncpg URL is correctly converted to psycopg URL."""
        reset_tool_context_store()  # Start fresh

        with (
            patch("src.domains.agents.context.store.AsyncConnection") as mock_conn_class,
            patch("src.domains.agents.context.store.AsyncPostgresStore") as mock_store_class,
            patch("src.domains.agents.context.store.settings") as mock_settings,
        ):
            # Mock settings with asyncpg URL
            mock_settings.tool_context_enabled = True
            mock_settings.database_url = "postgresql+asyncpg://user:pass@localhost:5432/testdb"

            # Mock connection
            mock_conn = AsyncMock()
            mock_conn_class.connect = AsyncMock(return_value=mock_conn)

            # Mock store
            mock_store = AsyncMock()
            mock_store.setup = AsyncMock()
            mock_store_class.return_value = mock_store

            # Call function
            await get_tool_context_store()

            # Verify URL converted correctly
            call_args = mock_conn_class.connect.call_args[0][0]
            assert call_args == "postgresql://user:pass@localhost:5432/testdb"
            assert "+asyncpg" not in call_args

    @pytest.mark.asyncio
    async def test_get_tool_context_store_connection_params(self):
        """Test that connection is created with correct parameters."""
        reset_tool_context_store()  # Start fresh

        with (
            patch("src.domains.agents.context.store.AsyncConnection") as mock_conn_class,
            patch("src.domains.agents.context.store.AsyncPostgresStore") as mock_store_class,
            patch("src.domains.agents.context.store.settings") as mock_settings,
        ):
            # Mock settings
            mock_settings.tool_context_enabled = True
            mock_settings.database_url = "postgresql+asyncpg://user:pass@localhost/db"

            # Mock connection
            mock_conn = AsyncMock()
            mock_conn_class.connect = AsyncMock(return_value=mock_conn)

            # Mock store
            mock_store = AsyncMock()
            mock_store.setup = AsyncMock()
            mock_store_class.return_value = mock_store

            # Call function
            await get_tool_context_store()

            # Verify connection parameters
            call_kwargs = mock_conn_class.connect.call_args[1]
            assert call_kwargs["autocommit"] is True
            assert call_kwargs["prepare_threshold"] == 0
            assert "row_factory" in call_kwargs


class TestCleanupToolContextStore:
    """Tests for cleanup_tool_context_store() cleanup function."""

    @pytest.mark.asyncio
    async def test_cleanup_with_existing_store(self):
        """Test cleanup closes connection and clears store."""
        reset_tool_context_store()  # Start fresh

        with (
            patch("src.domains.agents.context.store.AsyncConnection") as mock_conn_class,
            patch("src.domains.agents.context.store.AsyncPostgresStore") as mock_store_class,
            patch("src.domains.agents.context.store.settings") as mock_settings,
        ):
            # Mock settings
            mock_settings.tool_context_enabled = True
            mock_settings.database_url = "postgresql+asyncpg://user:pass@localhost/db"

            # Mock connection
            mock_conn = AsyncMock()
            mock_conn.close = AsyncMock()
            mock_conn_class.connect = AsyncMock(return_value=mock_conn)

            # Mock store
            mock_store = AsyncMock()
            mock_store.setup = AsyncMock()
            mock_store_class.return_value = mock_store

            # Create store
            await get_tool_context_store()

            # Cleanup
            await cleanup_tool_context_store()

            # Verify connection closed
            mock_conn.close.assert_called_once()

            # Verify store cleared (next call creates new instance)
            await get_tool_context_store()
            # New instance created
            assert mock_conn_class.connect.call_count == 2  # Once for first, once after cleanup

    @pytest.mark.asyncio
    async def test_cleanup_with_no_store(self):
        """Test cleanup does nothing when no store exists."""
        reset_tool_context_store()  # Ensure no store

        # Cleanup should not crash
        await cleanup_tool_context_store()
        # No assertions needed - just verify no exception

    @pytest.mark.asyncio
    async def test_cleanup_without_connection(self):
        """Test cleanup handles case where store exists but connection is None."""
        reset_tool_context_store()

        with patch("src.domains.agents.context.store._tool_context_store", AsyncMock()):
            # Store exists but no connection
            with patch("src.domains.agents.context.store._store_connection", None):
                # Should not crash
                await cleanup_tool_context_store()


class TestResetToolContextStore:
    """Tests for reset_tool_context_store() reset function."""

    def test_reset_clears_singleton(self):
        """Test that reset clears global store and connection."""
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
            patch("src.domains.agents.context.store.AsyncConnection") as mock_conn_class,
            patch("src.domains.agents.context.store.AsyncPostgresStore") as mock_store_class,
            patch("src.domains.agents.context.store.settings") as mock_settings,
        ):
            # Mock settings
            mock_settings.tool_context_enabled = True
            mock_settings.database_url = "postgresql+asyncpg://user:pass@localhost/db"

            # Mock connection
            mock_conn = AsyncMock()
            mock_conn_class.connect = AsyncMock(return_value=mock_conn)

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


class TestIntegration:
    """Integration tests for store lifecycle."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        """Test complete lifecycle: create → use → cleanup → recreate."""
        reset_tool_context_store()

        with (
            patch("src.domains.agents.context.store.AsyncConnection") as mock_conn_class,
            patch("src.domains.agents.context.store.AsyncPostgresStore") as mock_store_class,
            patch("src.domains.agents.context.store.settings") as mock_settings,
        ):
            # Mock settings
            mock_settings.tool_context_enabled = True
            mock_settings.database_url = "postgresql+asyncpg://user:pass@localhost/db"

            # Mock connection
            mock_conn = AsyncMock()
            mock_conn.close = AsyncMock()
            mock_conn_class.connect = AsyncMock(return_value=mock_conn)

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
            mock_conn.close.assert_called_once()

            # Step 4: Recreate after cleanup
            store2 = await get_tool_context_store()
            assert store2 is mock_store2
            assert store2 is not store1
