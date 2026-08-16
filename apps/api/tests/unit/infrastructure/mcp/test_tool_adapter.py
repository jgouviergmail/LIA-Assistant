"""
Unit tests for MCPToolAdapter.

Tests MCP → LangChain BaseTool conversion, schema generation,
tool invocation, error handling, and Prometheus metrics.

Phase: evolution F2 — MCP Support
Created: 2026-02-28
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.infrastructure.mcp.tool_adapter import MCPToolAdapter, build_args_schema


class TestBuildArgsSchema:
    """Test JSON Schema → Pydantic model conversion."""

    def test_basic_types(self):
        schema = {
            "properties": {
                "name": {"type": "string", "description": "Name"},
                "count": {"type": "integer", "description": "Count"},
                "ratio": {"type": "number", "description": "Ratio"},
                "active": {"type": "boolean", "description": "Active"},
            },
            "required": ["name"],
        }
        model = build_args_schema(schema)
        assert model is not None
        fields = model.model_fields
        assert "name" in fields
        assert "count" in fields
        assert "ratio" in fields
        assert "active" in fields

    def test_array_and_object(self):
        schema = {
            "properties": {
                "items": {"type": "array", "description": "Items list"},
                "metadata": {"type": "object", "description": "Metadata"},
            },
            "required": [],
        }
        model = build_args_schema(schema)
        assert model is not None

    def test_required_vs_optional(self):
        schema = {
            "properties": {
                "required_field": {"type": "string", "description": "Required"},
                "optional_field": {"type": "string", "description": "Optional"},
            },
            "required": ["required_field"],
        }
        model = build_args_schema(schema)
        assert model is not None
        fields = model.model_fields
        assert fields["required_field"].is_required()
        assert not fields["optional_field"].is_required()

    def test_complex_schema_fallback(self):
        """Complex schemas ($ref, allOf) should return None."""
        schema = {
            "properties": {
                "nested": {"$ref": "#/definitions/Nested"},
            },
            "required": [],
        }
        model = build_args_schema(schema)
        assert model is None

    def test_allof_fallback(self):
        schema = {
            "properties": {
                "field": {"allOf": [{"type": "string"}, {"minLength": 1}]},
            },
            "required": [],
        }
        model = build_args_schema(schema)
        assert model is None

    def test_empty_properties(self):
        schema = {"properties": {}}
        model = build_args_schema(schema)
        assert model is None

    def test_no_properties_key(self):
        schema = {"type": "object"}
        model = build_args_schema(schema)
        assert model is None


def _array_member(field_schema: dict) -> dict:
    """The array member of a field schema (unwraps the optional anyOf)."""
    if "anyOf" in field_schema:
        return next(m for m in field_schema["anyOf"] if m.get("type") == "array")
    return field_schema


class TestArrayItemsSchema:
    """Array properties must emit a TYPED ``items`` in their JSON schema.

    A bare ``list`` field emits ``items: {}``, which the Gemini converter turns
    into an untyped items proto the API rejects with 400 INVALID_ARGUMENT
    ("parameters.properties[urls].items: missing field") — one such tool
    poisons the ENTIRE bind, killing every ReAct iteration on Gemini models
    (prod 2026-08-14, react_reasoning_stream_failed). The adapter must carry
    the server-declared item type through, and default degraded/absent
    declarations to string items.
    """

    def test_declared_scalar_item_types_are_preserved(self):
        schema = {
            "properties": {
                "urls": {"type": "array", "items": {"type": "string"}, "description": "URLs"},
                "pageNumbers": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["urls"],
        }
        model = build_args_schema(schema)
        assert model is not None
        props = model.model_json_schema()["properties"]
        assert _array_member(props["urls"])["items"] == {"type": "string"}
        assert _array_member(props["pageNumbers"])["items"] == {"type": "integer"}

    def test_items_enum_is_preserved(self):
        schema = {
            "properties": {
                "formats": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["markdown", "html"]},
                },
            },
            "required": [],
        }
        model = build_args_schema(schema)
        assert model is not None
        items = _array_member(model.model_json_schema()["properties"]["formats"])["items"]
        assert items["type"] == "string"
        assert items["enum"] == ["markdown", "html"]

    def test_array_without_items_defaults_to_string_items(self):
        schema = {
            "properties": {"tags": {"type": "array", "description": "Tags"}},
            "required": [],
        }
        model = build_args_schema(schema)
        assert model is not None
        assert _array_member(model.model_json_schema()["properties"]["tags"])["items"] == {
            "type": "string"
        }

    def test_complex_items_degrade_to_string_items(self):
        """$ref / non-dict items cannot be forwarded reliably — degrade, don't drop."""
        schema = {
            "properties": {
                "refs": {"type": "array", "items": {"$ref": "#/defs/X"}},
                "weird": {"type": "array", "items": True},
            },
            "required": [],
        }
        model = build_args_schema(schema)
        assert model is not None
        props = model.model_json_schema()["properties"]
        assert _array_member(props["refs"])["items"] == {"type": "string"}
        assert _array_member(props["weird"])["items"] == {"type": "string"}

    def test_nested_array_items_stay_typed_at_every_level(self):
        schema = {
            "properties": {
                "matrix": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "integer"}},
                },
            },
            "required": [],
        }
        model = build_args_schema(schema)
        assert model is not None
        items = _array_member(model.model_json_schema()["properties"]["matrix"])["items"]
        assert items == {"type": "array", "items": {"type": "integer"}}

    def test_validation_stays_permissive(self):
        """The items annotation is SCHEMA-ONLY: runtime validation keeps
        accepting whatever the server accepted before (bare list)."""
        schema = {
            "properties": {"urls": {"type": "array", "items": {"type": "string"}}},
            "required": ["urls"],
        }
        model = build_args_schema(schema)
        assert model is not None
        # heterogeneous payload still validates — the boundary contract is the
        # MCP server's, not ours
        instance = model(urls=["a", 1, {"k": "v"}])
        assert instance.urls == ["a", 1, {"k": "v"}]

    def test_gemini_function_declaration_carries_items(self):
        """End-to-end oracle through the REAL Gemini converter: the exact
        failure mode of prod 2026-08-14 (items proto absent → API 400)."""
        from langchain_google_genai._function_utils import (
            convert_to_genai_function_declarations,
        )

        adapter = MCPToolAdapter.from_mcp_tool(
            server_name="firecrawl",
            tool_name="scrape",
            description="Scrape URLs",
            input_schema={
                "properties": {
                    "urls": {"type": "array", "items": {"type": "string"}},
                    "includeTags": {"type": "array"},
                },
                "required": ["urls"],
            },
        )
        out = convert_to_genai_function_declarations([adapter])
        tool = out[0] if isinstance(out, list) else out
        params = tool.function_declarations[0].parameters
        for prop_name in ("urls", "includeTags"):
            items = params.properties[prop_name].items
            assert items is not None, f"{prop_name}: items missing — Gemini rejects this bind"
            assert str(items.type) != "Type.TYPE_UNSPECIFIED"


class TestMCPToolAdapterFromMcpTool:
    """Test MCPToolAdapter.from_mcp_tool() factory."""

    def test_name_prefixing(self):
        adapter = MCPToolAdapter.from_mcp_tool(
            server_name="filesystem",
            tool_name="read_file",
            description="Read a file",
            input_schema={"properties": {"path": {"type": "string"}}, "required": ["path"]},
        )
        assert adapter.name == "mcp_filesystem_read_file"
        assert adapter.server_name == "filesystem"
        assert adapter.mcp_tool_name == "read_file"
        assert adapter.description == "Read a file"

    def test_args_schema_generated(self):
        adapter = MCPToolAdapter.from_mcp_tool(
            server_name="db",
            tool_name="query",
            description="Run SQL query",
            input_schema={
                "properties": {
                    "sql": {"type": "string", "description": "SQL statement"},
                    "limit": {"type": "integer", "description": "Row limit"},
                },
                "required": ["sql"],
            },
        )
        assert adapter.args_schema is not None
        assert "sql" in adapter.args_schema.model_fields

    def test_args_schema_none_for_complex(self):
        adapter = MCPToolAdapter.from_mcp_tool(
            server_name="test",
            tool_name="complex",
            description="Complex tool",
            input_schema={
                "properties": {"data": {"$ref": "#/defs/Data"}},
                "required": [],
            },
        )
        assert adapter.args_schema is None


class TestMCPToolAdapterArun:
    """Test MCPToolAdapter._arun() execution."""

    @pytest.fixture
    def adapter(self):
        return MCPToolAdapter.from_mcp_tool(
            server_name="test_server",
            tool_name="test_tool",
            description="Test tool",
            input_schema={"properties": {"arg1": {"type": "string"}}, "required": ["arg1"]},
        )

    @pytest.mark.asyncio
    async def test_successful_call(self, adapter):
        from src.domains.agents.tools.output import UnifiedToolOutput

        mock_manager = AsyncMock()
        mock_manager.call_tool = AsyncMock(return_value='{"result": "success"}')

        with patch(
            "src.infrastructure.mcp.client_manager.get_mcp_client_manager",
            return_value=mock_manager,
        ):
            result = await adapter._arun(arg1="test_value")

        assert isinstance(result, UnifiedToolOutput)
        assert result.success is True
        assert result.structured_data["result"] == '{"result": "success"}'
        mock_manager.call_tool.assert_called_once_with(
            "test_server", "test_tool", {"arg1": "test_value"}
        )

    @pytest.mark.asyncio
    async def test_manager_not_initialized(self, adapter):
        with patch(
            "src.infrastructure.mcp.client_manager.get_mcp_client_manager",
            return_value=None,
        ):
            with pytest.raises(RuntimeError, match="not initialized"):
                await adapter._arun(arg1="test")

    @pytest.mark.asyncio
    async def test_error_propagated(self, adapter):
        mock_manager = AsyncMock()
        mock_manager.call_tool = AsyncMock(side_effect=RuntimeError("Server disconnected"))

        with patch(
            "src.infrastructure.mcp.client_manager.get_mcp_client_manager",
            return_value=mock_manager,
        ):
            with pytest.raises(RuntimeError, match="disconnected"):
                await adapter._arun(arg1="test")

    @pytest.mark.asyncio
    async def test_timeout_propagated(self, adapter):
        import asyncio

        mock_manager = AsyncMock()
        mock_manager.call_tool = AsyncMock(side_effect=TimeoutError())

        with patch(
            "src.infrastructure.mcp.client_manager.get_mcp_client_manager",
            return_value=mock_manager,
        ):
            with pytest.raises(asyncio.TimeoutError):
                await adapter._arun(arg1="test")

    @pytest.mark.asyncio
    async def test_metrics_incremented_on_success(self, adapter):
        mock_manager = AsyncMock()
        mock_manager.call_tool = AsyncMock(return_value="ok")

        with (
            patch(
                "src.infrastructure.mcp.client_manager.get_mcp_client_manager",
                return_value=mock_manager,
            ),
            patch("src.infrastructure.mcp.tool_adapter.mcp_tool_invocations_total") as mock_counter,
            patch(
                "src.infrastructure.mcp.tool_adapter.mcp_tool_duration_seconds"
            ) as mock_histogram,
        ):
            await adapter._arun(arg1="test")
            mock_counter.labels.assert_called_with(
                server_name="test_server",
                tool_name="test_tool",
                status="success",
            )
            mock_histogram.labels.assert_called_with(
                server_name="test_server",
                tool_name="test_tool",
            )

    @pytest.mark.asyncio
    async def test_metrics_incremented_on_error(self, adapter):
        mock_manager = AsyncMock()
        mock_manager.call_tool = AsyncMock(side_effect=RuntimeError("fail"))

        with (
            patch(
                "src.infrastructure.mcp.client_manager.get_mcp_client_manager",
                return_value=mock_manager,
            ),
            patch("src.infrastructure.mcp.tool_adapter.mcp_tool_invocations_total") as mock_counter,
            patch(
                "src.infrastructure.mcp.tool_adapter.mcp_connection_errors_total"
            ) as _mock_errors,
        ):
            with pytest.raises(RuntimeError):
                await adapter._arun(arg1="test")

            # Check error status was tracked
            calls = mock_counter.labels.call_args_list
            assert any(
                call.kwargs.get("status") == "error"
                or (len(call.args) >= 3 and call.args[2] == "error")
                for call in calls
            )


class TestMCPToolAdapterRun:
    """Test sync _run() raises NotImplementedError."""

    def test_run_raises(self):
        adapter = MCPToolAdapter.from_mcp_tool(
            server_name="test",
            tool_name="test",
            description="Test",
            input_schema={},
        )
        with pytest.raises(NotImplementedError, match="async only"):
            adapter._run()
