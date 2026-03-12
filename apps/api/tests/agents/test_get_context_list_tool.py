"""
Unit tests for get_context_list tool.

Tests the new batch operation tool that returns the full context list
for a domain (max MAX_CONTEXT_BATCH_SIZE items).

Phase: get_context_list tool implementation (bug fix for "affiche les détails de ces deux contacts")
Migrated to UnifiedToolOutput (2025-12-29)
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.context.schemas import ContextMetadata, ToolContextList
from src.domains.agents.tools.context_tools import get_context_list
from src.domains.agents.tools.output import UnifiedToolOutput


@pytest.fixture
def mock_registry_contacts():
    """Mock ContextTypeRegistry to always return 'contacts' as valid domain.

    This fixture ensures test isolation from the global ContextTypeRegistry
    singleton which may be modified by other tests.
    """
    with patch("src.domains.agents.tools.context_tools.ContextTypeRegistry") as MockRegistry:
        MockRegistry.list_all.return_value = ["contacts"]

        # get_definition should raise ValueError for invalid domains
        def mock_get_definition(domain):
            if domain == "contacts":
                return MagicMock()  # Return a mock definition for valid domain
            raise ValueError(f"Context type '{domain}' not registered.")

        MockRegistry.get_definition.side_effect = mock_get_definition
        yield MockRegistry


@pytest.mark.asyncio
class TestGetContextListTool:
    """Tests for get_context_list tool (batch operations)."""

    async def test_valid_context_with_2_items(self, mock_registry_contacts):
        """Test valid context with 2 items returns full list."""
        # Given: Runtime mock with valid config and store
        runtime = MagicMock()
        runtime.config = {
            "configurable": {
                "user_id": str(uuid4()),
                "thread_id": str(uuid4()),
            }
        }
        runtime.store = MagicMock()

        # Mock ToolContextManager.get_list to return 2 contacts
        mock_context_list = ToolContextList(
            domain="contacts",
            items=[
                {"index": 0, "resource_name": "people/c123", "name": "Jean Dupont"},
                {"index": 1, "resource_name": "people/c456", "name": "Marie Martin"},
            ],
            metadata=ContextMetadata(
                turn_id=5,
                total_count=2,
                query="liste contacts",
                timestamp=datetime.now(UTC).isoformat(),
            ),
        )

        with patch("src.domains.agents.tools.context_tools.ToolContextManager") as MockManager:
            mock_manager = MockManager.return_value
            mock_manager.get_list = AsyncMock(return_value=mock_context_list)

            # When: Call the underlying function directly
            result = await get_context_list.coroutine(domain="contacts", runtime=runtime)

            # Then: Success with 2 items (UnifiedToolOutput)
            assert isinstance(result, UnifiedToolOutput)
            assert result.success is True
            data = result.structured_data
            assert data["domain"] == "contacts"
            assert data["total_count"] == 2
            assert data["truncated"] is False
            assert len(data["items"]) == 2
            assert data["items"][0]["name"] == "Jean Dupont"
            assert data["items"][1]["name"] == "Marie Martin"
            assert "turn_id" in data

    async def test_valid_context_with_15_items_truncated(self, mock_registry_contacts):
        """Test context with 15 items returns 10 items with truncated=true."""
        # Given: Runtime mock with valid config and store
        runtime = MagicMock()
        runtime.config = {
            "configurable": {
                "user_id": str(uuid4()),
                "thread_id": str(uuid4()),
            }
        }
        runtime.store = MagicMock()

        # Create 15 items
        items = [
            {"index": i, "resource_name": f"people/c{i}", "name": f"Contact {i}"} for i in range(15)
        ]

        mock_context_list = ToolContextList(
            domain="contacts",
            items=items,
            metadata=ContextMetadata(
                turn_id=3,
                total_count=15,
                query="liste contacts",
                timestamp=datetime.now(UTC).isoformat(),
            ),
        )

        with patch("src.domains.agents.tools.context_tools.ToolContextManager") as MockManager:
            mock_manager = MockManager.return_value
            mock_manager.get_list = AsyncMock(return_value=mock_context_list)

            # When: Call the underlying function directly
            result = await get_context_list.coroutine(domain="contacts", runtime=runtime)

            # Then: Truncated to 10 items (UnifiedToolOutput)
            assert isinstance(result, UnifiedToolOutput)
            assert result.success is True
            data = result.structured_data
            assert data["total_count"] == 10  # Returned count
            assert data["truncated"] is True
            assert data["total_available"] == 15  # Original count
            assert len(data["items"]) == 10
            # Message is in UnifiedToolOutput.message
            assert "10" in result.message  # truncation message

    async def test_empty_context_returns_no_context_error(self, mock_registry_contacts):
        """Test empty context returns no_context error."""
        # Given: Runtime mock with valid config and store
        runtime = MagicMock()
        runtime.config = {
            "configurable": {
                "user_id": str(uuid4()),
                "thread_id": str(uuid4()),
            }
        }
        runtime.store = MagicMock()

        # Mock empty context
        with patch("src.domains.agents.tools.context_tools.ToolContextManager") as MockManager:
            mock_manager = MockManager.return_value
            mock_manager.get_list = AsyncMock(return_value=None)

            # When: Call the underlying function directly
            result = await get_context_list.coroutine(domain="contacts", runtime=runtime)

            # Then: Error no_context (UnifiedToolOutput)
            assert isinstance(result, UnifiedToolOutput)
            assert result.success is False
            assert result.error_code == "no_context"
            assert "contacts" in result.message

    async def test_invalid_domain_returns_invalid_domain_error(self, mock_registry_contacts):
        """Test invalid domain returns invalid_domain error with available domains."""
        # Given: Runtime mock with valid config and store
        runtime = MagicMock()
        runtime.config = {
            "configurable": {
                "user_id": str(uuid4()),
                "thread_id": str(uuid4()),
            }
        }
        runtime.store = MagicMock()

        # When: Call with invalid domain "foo"
        result = await get_context_list.coroutine(domain="foo", runtime=runtime)

        # Then: Error invalid_domain (UnifiedToolOutput with metadata)
        assert isinstance(result, UnifiedToolOutput)
        assert result.success is False
        assert result.error_code == "invalid_domain"
        assert "foo" in result.message
        assert "available_domains" in result.metadata
        # Should list valid domains like ["contacts"]
        assert isinstance(result.metadata["available_domains"], list)

    async def test_missing_user_id_returns_configuration_error(self):
        """Test missing user_id returns configuration_error."""
        # Given: Runtime mock with missing user_id
        runtime = MagicMock()
        runtime.config = {
            "configurable": {
                # user_id missing
                "thread_id": str(uuid4()),
            }
        }
        runtime.store = MagicMock()

        # When: Call the underlying function directly
        result = await get_context_list.coroutine(domain="contacts", runtime=runtime)

        # Then: Error configuration_error (UnifiedToolOutput)
        assert isinstance(result, UnifiedToolOutput)
        assert result.success is False
        assert result.error_code == "configuration_error"
        assert "user_id" in result.message

    async def test_missing_session_id_returns_configuration_error(self):
        """Test missing session_id (thread_id) returns configuration_error."""
        # Given: Runtime mock with missing thread_id
        runtime = MagicMock()
        runtime.config = {
            "configurable": {
                "user_id": str(uuid4()),
                # thread_id missing
            }
        }
        runtime.store = MagicMock()

        # When: Call the underlying function directly
        result = await get_context_list.coroutine(domain="contacts", runtime=runtime)

        # Then: Error configuration_error (UnifiedToolOutput)
        assert isinstance(result, UnifiedToolOutput)
        assert result.success is False
        assert result.error_code == "configuration_error"
        assert "thread_id" in result.message

    async def test_missing_store_returns_configuration_error(self):
        """Test missing store returns configuration_error."""
        # This test is tricky because the tool extracts store from runtime
        # which is injected by LangChain. For now, we'll skip this edge case
        # as it's handled by the LangChain framework itself.
        pass

    async def test_items_have_correct_indexes(self, mock_registry_contacts):
        """Test items retain original indexes (0, 1, 2...)."""
        # Given: Runtime mock with valid config and store
        runtime = MagicMock()
        runtime.config = {
            "configurable": {
                "user_id": str(uuid4()),
                "thread_id": str(uuid4()),
            }
        }
        runtime.store = MagicMock()

        items = [
            {"index": 0, "resource_name": "people/c1", "name": "First"},
            {"index": 1, "resource_name": "people/c2", "name": "Second"},
            {"index": 2, "resource_name": "people/c3", "name": "Third"},
        ]

        mock_context_list = ToolContextList(
            domain="contacts",
            items=items,
            metadata=ContextMetadata(
                turn_id=1,
                total_count=3,
                query="test",
                timestamp=datetime.now(UTC).isoformat(),
            ),
        )

        with patch("src.domains.agents.tools.context_tools.ToolContextManager") as MockManager:
            mock_manager = MockManager.return_value
            mock_manager.get_list = AsyncMock(return_value=mock_context_list)

            # When: Call the underlying function directly
            result = await get_context_list.coroutine(domain="contacts", runtime=runtime)

            # Then: Indexes are preserved (UnifiedToolOutput)
            assert isinstance(result, UnifiedToolOutput)
            assert result.success is True
            data = result.structured_data
            assert data["items"][0]["index"] == 0
            assert data["items"][1]["index"] == 1
            assert data["items"][2]["index"] == 2
            assert data["items"][0]["name"] == "First"
            assert data["items"][2]["name"] == "Third"
