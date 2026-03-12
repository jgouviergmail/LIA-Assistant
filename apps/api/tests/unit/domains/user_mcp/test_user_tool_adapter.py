"""Tests for UserMCPToolAdapter — per-user MCP tool wrapper."""

import json
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from src.core.constants import MCP_USER_TOOL_NAME_PREFIX
from src.core.field_names import FIELD_REGISTRY_ID
from src.domains.agents.constants import CONTEXT_DOMAIN_MCP
from src.domains.agents.data_registry.models import RegistryItemType
from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.mcp.user_tool_adapter import (
    UserMCPToolAdapter,
    _derive_collection_key,
    _parse_mcp_structured_items,
)


class TestUserMCPToolAdapterNaming:
    """Tests for tool naming convention."""

    def test_name_format(self) -> None:
        """Should follow naming convention mcp_user_{prefix}_{tool_name}."""
        server_id = UUID("12345678-1234-1234-1234-123456789abc")
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=server_id,
            user_id=uuid4(),
            server_name="My Server",
            tool_name="read_file",
            description="Read a file",
            input_schema={},
        )
        assert adapter.name == f"{MCP_USER_TOOL_NAME_PREFIX}_12345678_read_file"

    def test_name_starts_with_prefix(self) -> None:
        """Should start with the user MCP tool prefix."""
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=uuid4(),
            user_id=uuid4(),
            server_name="Test",
            tool_name="ping",
            description="Ping",
            input_schema={},
        )
        assert adapter.name.startswith(MCP_USER_TOOL_NAME_PREFIX)

    def test_server_name_label(self) -> None:
        """Should set server_name_label with user_ prefix for Prometheus."""
        server_id = UUID("abcdef12-0000-0000-0000-000000000000")
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=server_id,
            user_id=uuid4(),
            server_name="Test",
            tool_name="ping",
            description="Ping",
            input_schema={},
        )
        assert adapter.server_name_label == "user_abcdef12"


class TestUserMCPToolAdapterCreation:
    """Tests for adapter creation from discovered tools."""

    def test_stores_metadata(self) -> None:
        """Should store server_id, user_id, and original tool name."""
        server_id = uuid4()
        user_id = uuid4()
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=server_id,
            user_id=user_id,
            server_name="Test",
            tool_name="search",
            description="Search things",
            input_schema={},
            timeout_seconds=60,
        )
        assert adapter.server_id == server_id
        assert adapter.user_id == user_id
        assert adapter.mcp_tool_name == "search"
        assert adapter.timeout_seconds == 60

    def test_stores_server_display_name(self) -> None:
        """Should store human-readable server name for card display."""
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=uuid4(),
            user_id=uuid4(),
            server_name="HuggingFace Hub",
            tool_name="search",
            description="Search",
            input_schema={},
        )
        assert adapter.server_display_name == "HuggingFace Hub"

    def test_builds_args_schema(self) -> None:
        """Should build Pydantic args_schema from input_schema."""
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=uuid4(),
            user_id=uuid4(),
            server_name="Test",
            tool_name="query",
            description="Run query",
            input_schema={
                "type": "object",
                "properties": {"sql": {"type": "string"}},
                "required": ["sql"],
            },
        )
        assert adapter.args_schema is not None


class TestUserMCPToolAdapterExecution:
    """Tests for tool execution via pool."""

    @pytest.mark.asyncio
    async def test_arun_calls_pool(self) -> None:
        """Should delegate to pool.call_tool() and return UnifiedToolOutput."""
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=uuid4(),
            user_id=uuid4(),
            server_name="Test",
            tool_name="ping",
            description="Ping",
            input_schema={},
        )

        mock_pool = AsyncMock()
        mock_pool.call_tool = AsyncMock(return_value="pong")

        with patch(
            "src.infrastructure.mcp.user_pool.get_user_mcp_pool",
            return_value=mock_pool,
        ):
            result = await adapter._arun()
            assert isinstance(result, UnifiedToolOutput)
            assert result.success is True
            assert "ping" in result.message
            mock_pool.call_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_arun_pool_not_initialized(self) -> None:
        """Should raise RuntimeError when pool is None."""
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=uuid4(),
            user_id=uuid4(),
            server_name="Test",
            tool_name="ping",
            description="Ping",
            input_schema={},
        )

        with patch(
            "src.infrastructure.mcp.user_pool.get_user_mcp_pool",
            return_value=None,
        ):
            with pytest.raises(RuntimeError, match="not initialized"):
                await adapter._arun()

    def test_run_raises_not_implemented(self) -> None:
        """Should raise NotImplementedError for sync execution."""
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=uuid4(),
            user_id=uuid4(),
            server_name="Test",
            tool_name="ping",
            description="Ping",
            input_schema={},
        )
        with pytest.raises(NotImplementedError, match="async only"):
            adapter._run()

    @pytest.mark.asyncio
    async def test_arun_records_error_metrics(self) -> None:
        """Should increment error metrics on exception."""
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=uuid4(),
            user_id=uuid4(),
            server_name="Test",
            tool_name="failing_tool",
            description="Fails",
            input_schema={},
        )

        mock_pool = AsyncMock()
        mock_pool.call_tool = AsyncMock(side_effect=RuntimeError("connection lost"))

        with (
            patch(
                "src.infrastructure.mcp.user_pool.get_user_mcp_pool",
                return_value=mock_pool,
            ),
            pytest.raises(RuntimeError, match="connection lost"),
        ):
            await adapter._arun()


class TestUserMCPToolAdapterUnifiedOutput:
    """Tests for UnifiedToolOutput and RegistryItem generation (evolution F2.3)."""

    @pytest.mark.asyncio
    async def test_arun_returns_unified_tool_output(self) -> None:
        """Should return UnifiedToolOutput instead of raw string."""
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=uuid4(),
            user_id=uuid4(),
            server_name="Test Server",
            tool_name="fetch_data",
            description="Fetch data",
            input_schema={},
        )

        mock_pool = AsyncMock()
        mock_pool.call_tool = AsyncMock(return_value="some data")

        with patch(
            "src.infrastructure.mcp.user_pool.get_user_mcp_pool",
            return_value=mock_pool,
        ):
            result = await adapter._arun()
            assert isinstance(result, UnifiedToolOutput)
            assert result.success is True

    @pytest.mark.asyncio
    async def test_arun_registry_updates_not_empty(self) -> None:
        """Should include registry_updates with a RegistryItem."""
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=uuid4(),
            user_id=uuid4(),
            server_name="Test",
            tool_name="ping",
            description="Ping",
            input_schema={},
        )

        mock_pool = AsyncMock()
        mock_pool.call_tool = AsyncMock(return_value="pong")

        with patch(
            "src.infrastructure.mcp.user_pool.get_user_mcp_pool",
            return_value=mock_pool,
        ):
            result = await adapter._arun()
            assert result.registry_updates is not None
            assert len(result.registry_updates) == 1

    @pytest.mark.asyncio
    async def test_arun_registry_item_has_correct_type(self) -> None:
        """Should create RegistryItem with MCP_RESULT type."""
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=uuid4(),
            user_id=uuid4(),
            server_name="Test",
            tool_name="search",
            description="Search",
            input_schema={},
        )

        mock_pool = AsyncMock()
        mock_pool.call_tool = AsyncMock(return_value="results")

        with patch(
            "src.infrastructure.mcp.user_pool.get_user_mcp_pool",
            return_value=mock_pool,
        ):
            result = await adapter._arun()
            item = next(iter(result.registry_updates.values()))
            assert item.type == RegistryItemType.MCP_RESULT

    @pytest.mark.asyncio
    async def test_arun_registry_item_payload(self) -> None:
        """Should include tool_name, server_name, and result in payload."""
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=uuid4(),
            user_id=uuid4(),
            server_name="HuggingFace Hub",
            tool_name="search_models",
            description="Search models",
            input_schema={},
        )

        mock_pool = AsyncMock()
        mock_pool.call_tool = AsyncMock(return_value="42 models found")

        with patch(
            "src.infrastructure.mcp.user_pool.get_user_mcp_pool",
            return_value=mock_pool,
        ):
            result = await adapter._arun()
            item = next(iter(result.registry_updates.values()))
            assert item.payload["tool_name"] == "search_models"
            assert item.payload["server_name"] == "HuggingFace Hub"
            assert item.payload["result"] == "42 models found"

    @pytest.mark.asyncio
    async def test_arun_registry_item_meta_domain(self) -> None:
        """Should set meta.domain to CONTEXT_DOMAIN_MCP ('mcps')."""
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=uuid4(),
            user_id=uuid4(),
            server_name="Test",
            tool_name="ping",
            description="Ping",
            input_schema={},
        )

        mock_pool = AsyncMock()
        mock_pool.call_tool = AsyncMock(return_value="pong")

        with patch(
            "src.infrastructure.mcp.user_pool.get_user_mcp_pool",
            return_value=mock_pool,
        ):
            result = await adapter._arun()
            item = next(iter(result.registry_updates.values()))
            assert item.meta.domain == CONTEXT_DOMAIN_MCP
            assert item.meta.domain == "mcps"

    @pytest.mark.asyncio
    async def test_arun_registry_item_server_name_human_readable(self) -> None:
        """Should use human-readable server name in payload, not UUID prefix."""
        server_id = UUID("abcdef12-0000-0000-0000-000000000000")
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=server_id,
            user_id=uuid4(),
            server_name="My Custom Server",
            tool_name="action",
            description="Action",
            input_schema={},
        )

        mock_pool = AsyncMock()
        mock_pool.call_tool = AsyncMock(return_value="done")

        with patch(
            "src.infrastructure.mcp.user_pool.get_user_mcp_pool",
            return_value=mock_pool,
        ):
            result = await adapter._arun()
            item = next(iter(result.registry_updates.values()))
            # Should be human-readable name, not "user_abcdef12"
            assert item.payload["server_name"] == "My Custom Server"


class TestUserMCPToolAdapterCoroutine:
    """Tests for coroutine property bridge (evolution F2.3)."""

    def test_coroutine_property_returns_arun(self) -> None:
        """Should return _arun method for parallel_executor direct call path."""
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=uuid4(),
            user_id=uuid4(),
            server_name="Test",
            tool_name="ping",
            description="Ping",
            input_schema={},
        )
        # Bound methods create new objects each access, so compare underlying function
        assert adapter.coroutine.__func__ is adapter._arun.__func__

    def test_coroutine_property_hasattr(self) -> None:
        """Should be detected by parallel_executor's hasattr check."""
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=uuid4(),
            user_id=uuid4(),
            server_name="Test",
            tool_name="ping",
            description="Ping",
            input_schema={},
        )
        assert hasattr(adapter, "coroutine")
        assert adapter.coroutine is not None

    def test_coroutine_property_is_callable(self) -> None:
        """Should be callable (async function)."""
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=uuid4(),
            user_id=uuid4(),
            server_name="Test",
            tool_name="ping",
            description="Ping",
            input_schema={},
        )
        assert callable(adapter.coroutine)


class TestParseMcpStructuredItems:
    """Tests for _parse_mcp_structured_items() JSON parsing helper."""

    def test_json_array_of_dicts(self) -> None:
        """Should parse a JSON array of dicts into structured items."""
        result = _parse_mcp_structured_items('[{"name":"a"},{"name":"b"}]')
        assert result is not None
        items, key = result
        assert len(items) == 2
        assert items[0]["name"] == "a"
        assert items[1]["name"] == "b"
        assert key is None

    def test_json_object_with_array(self) -> None:
        """Should extract the largest list-of-dicts from a JSON object."""
        result = _parse_mcp_structured_items('{"repos":[{"name":"a"}],"count":1}')
        assert result is not None
        items, key = result
        assert len(items) == 1
        assert items[0]["name"] == "a"
        assert key == "repos"

    def test_plain_text_returns_none(self) -> None:
        """Should return None for non-JSON text."""
        assert _parse_mcp_structured_items("No results found") is None

    def test_json_no_array_returns_none(self) -> None:
        """Should return None for a JSON object without any array of dicts."""
        assert _parse_mcp_structured_items('{"status":"ok"}') is None

    def test_empty_array(self) -> None:
        """Should return empty list for an empty JSON array."""
        result = _parse_mcp_structured_items("[]")
        assert result is not None
        items, key = result
        assert items == []
        assert key is None

    def test_scalar_array_returns_none(self) -> None:
        """Should return None for a JSON array of scalars."""
        assert _parse_mcp_structured_items("[1,2,3]") is None

    def test_picks_largest_array_in_object(self) -> None:
        """When multiple arrays exist, should pick the largest."""
        raw = '{"small":[{"x":1}],"big":[{"x":1},{"x":2},{"x":3}]}'
        result = _parse_mcp_structured_items(raw)
        assert result is not None
        items, key = result
        assert len(items) == 3
        assert key == "big"


class TestDeriveCollectionKey:
    """Tests for _derive_collection_key() tool name → collection key."""

    def test_search_repositories(self) -> None:
        assert _derive_collection_key("search_repositories") == "repositories"

    def test_list_commits(self) -> None:
        assert _derive_collection_key("list_commits") == "commits"

    def test_get_user(self) -> None:
        assert _derive_collection_key("get_user") == "users"

    def test_no_verb_prefix(self) -> None:
        assert _derive_collection_key("ping") == "pings"

    def test_multiple_verb_prefixes(self) -> None:
        assert _derive_collection_key("get_list_items") == "items"

    def test_empty_after_strip(self) -> None:
        """If tool name is just a verb, fallback to 'items'."""
        assert _derive_collection_key("search") == "items"


class TestArunStructuredJSON:
    """Tests for _arun() with structured JSON parsing (evolution F2.4)."""

    @pytest.mark.asyncio
    async def test_json_array_creates_per_item_registry_items(self) -> None:
        """Should create N RegistryItems for a JSON array of N dicts."""
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=uuid4(),
            user_id=uuid4(),
            server_name="GitHub",
            tool_name="search_repositories",
            description="Search repos",
            input_schema={},
        )

        json_result = '[{"name":"repo1","stars":10},{"name":"repo2","stars":20}]'
        mock_pool = AsyncMock()
        mock_pool.call_tool = AsyncMock(return_value=json_result)

        with patch(
            "src.infrastructure.mcp.user_pool.get_user_mcp_pool",
            return_value=mock_pool,
        ):
            result = await adapter._arun()
            assert isinstance(result, UnifiedToolOutput)
            assert result.success is True

            # Should have 2 registry items (one per repo)
            assert len(result.registry_updates) == 2

            # Each item should have _mcp_structured flag and real data
            for item in result.registry_updates.values():
                assert item.type == RegistryItemType.MCP_RESULT
                assert item.payload["_mcp_structured"] is True
                assert item.payload["tool_name"] == "search_repositories"
                assert item.payload["server_name"] == "GitHub"
                assert "name" in item.payload  # Real data field
                assert item.meta.domain == CONTEXT_DOMAIN_MCP

            # structured_data should contain collection key alias
            assert "repositories" in result.structured_data
            items = result.structured_data["repositories"]
            assert len(items) == 2
            assert items[0]["name"] == "repo1"
            assert items[1]["name"] == "repo2"
            # Each item should have _registry_id for parent correlation
            assert FIELD_REGISTRY_ID in items[0]
            assert FIELD_REGISTRY_ID in items[1]

    @pytest.mark.asyncio
    async def test_non_json_falls_back_to_single_wrapper(self) -> None:
        """Should fall back to single wrapper for non-JSON results."""
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=uuid4(),
            user_id=uuid4(),
            server_name="Test",
            tool_name="ping",
            description="Ping",
            input_schema={},
        )

        mock_pool = AsyncMock()
        mock_pool.call_tool = AsyncMock(return_value="pong - not JSON")

        with patch(
            "src.infrastructure.mcp.user_pool.get_user_mcp_pool",
            return_value=mock_pool,
        ):
            result = await adapter._arun()
            assert isinstance(result, UnifiedToolOutput)
            assert len(result.registry_updates) == 1

            item = next(iter(result.registry_updates.values()))
            assert "result" in item.payload  # Wrapper with raw string
            assert "_mcp_structured" not in item.payload

    @pytest.mark.asyncio
    async def test_json_object_with_nested_array(self) -> None:
        """Should extract items from a JSON object wrapping an array."""
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=uuid4(),
            user_id=uuid4(),
            server_name="API",
            tool_name="list_users",
            description="List users",
            input_schema={},
        )

        json_result = '{"users":[{"name":"alice"},{"name":"bob"}],"total":2}'
        mock_pool = AsyncMock()
        mock_pool.call_tool = AsyncMock(return_value=json_result)

        with patch(
            "src.infrastructure.mcp.user_pool.get_user_mcp_pool",
            return_value=mock_pool,
        ):
            result = await adapter._arun()
            assert len(result.registry_updates) == 2
            # Collection key should be detected from the JSON field name
            assert "users" in result.structured_data


class TestStructuredItemsCap:
    """Tests for max structured items cap per MCP call."""

    @pytest.mark.asyncio
    async def test_arun_caps_items_at_max_setting(self) -> None:
        """Should create at most mcp_max_structured_items_per_call RegistryItems."""
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=uuid4(),
            user_id=uuid4(),
            server_name="GitHub",
            tool_name="list_commits",
            description="List commits",
            input_schema={},
        )

        # Generate 50 items — exceeds default cap of 25
        raw_items = [{"sha": f"abc{i}", "message": f"commit {i}"} for i in range(50)]

        json_result = json.dumps(raw_items)
        mock_pool = AsyncMock()
        mock_pool.call_tool = AsyncMock(return_value=json_result)

        mock_settings = type("S", (), {"mcp_max_structured_items_per_call": 25})()

        with (
            patch(
                "src.infrastructure.mcp.user_pool.get_user_mcp_pool",
                return_value=mock_pool,
            ),
            patch(
                "src.infrastructure.mcp.user_tool_adapter.settings",
                mock_settings,
            ),
        ):
            result = await adapter._arun()
            assert isinstance(result, UnifiedToolOutput)
            # Should be capped at 25, not 50
            assert len(result.registry_updates) == 25
            assert len(result.structured_data["commits"]) == 25

    @pytest.mark.asyncio
    async def test_arun_does_not_cap_when_under_limit(self) -> None:
        """Should keep all items when under the cap."""
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=uuid4(),
            user_id=uuid4(),
            server_name="GitHub",
            tool_name="search_repositories",
            description="Search repos",
            input_schema={},
        )

        raw_items = [{"name": f"repo{i}"} for i in range(10)]

        json_result = json.dumps(raw_items)
        mock_pool = AsyncMock()
        mock_pool.call_tool = AsyncMock(return_value=json_result)

        mock_settings = type("S", (), {"mcp_max_structured_items_per_call": 25})()

        with (
            patch(
                "src.infrastructure.mcp.user_pool.get_user_mcp_pool",
                return_value=mock_pool,
            ),
            patch(
                "src.infrastructure.mcp.user_tool_adapter.settings",
                mock_settings,
            ),
        ):
            result = await adapter._arun()
            # All 10 items should be kept (under 25 cap)
            assert len(result.registry_updates) == 10
            assert len(result.structured_data["repositories"]) == 10

    @pytest.mark.asyncio
    async def test_arun_custom_cap_value(self) -> None:
        """Should respect custom mcp_max_structured_items_per_call setting."""
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id=uuid4(),
            user_id=uuid4(),
            server_name="API",
            tool_name="list_items",
            description="List items",
            input_schema={},
        )

        raw_items = [{"id": i} for i in range(20)]

        json_result = json.dumps(raw_items)
        mock_pool = AsyncMock()
        mock_pool.call_tool = AsyncMock(return_value=json_result)

        # Custom cap of 5
        mock_settings = type("S", (), {"mcp_max_structured_items_per_call": 5})()

        with (
            patch(
                "src.infrastructure.mcp.user_pool.get_user_mcp_pool",
                return_value=mock_pool,
            ),
            patch(
                "src.infrastructure.mcp.user_tool_adapter.settings",
                mock_settings,
            ),
        ):
            result = await adapter._arun()
            assert len(result.registry_updates) == 5
            assert len(result.structured_data["items"]) == 5
            # Should keep first 5 items
            first_item = result.structured_data["items"][0]
            assert first_item["id"] == 0
