"""
Unit tests for MCP registration bridge.

Tests dual-registry registration (AgentRegistry + tool_registry),
manifest generation, and JSON Schema parameter conversion.

Phase: evolution F2 — MCP Support
Created: 2026-02-28
"""

from unittest.mock import MagicMock, patch

from src.domains.agents.constants import AGENT_MCP, CONTEXT_DOMAIN_MCP
from src.infrastructure.mcp.registration import (
    _compact_json_schema,
    _json_schema_to_parameters,
    _mcp_tool_to_manifest,
    register_mcp_tools,
)
from src.infrastructure.mcp.schemas import MCPDiscoveredTool, MCPServerConfig, MCPTransportType
from src.infrastructure.mcp.tool_adapter import MCPToolAdapter


class TestMcpToolToManifest:
    """Test ToolManifest generation from MCP tools."""

    def test_agent_is_mcp_agent(self):
        """All MCP tools must use the single virtual agent 'mcp_agent'."""
        discovered = MCPDiscoveredTool(
            server_name="filesystem",
            tool_name="read_file",
            description="Read a file from disk",
            input_schema={
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        )
        manifest = _mcp_tool_to_manifest(
            discovered=discovered,
            adapter_name="mcp_filesystem_read_file",
            hitl_required=True,
        )
        assert manifest.agent == AGENT_MCP

    def test_context_key_set(self):
        """ToolManifest must have context_key matching DomainConfig.result_key."""
        discovered = MCPDiscoveredTool(
            server_name="test",
            tool_name="tool",
            description="A test tool",
        )
        manifest = _mcp_tool_to_manifest(
            discovered=discovered,
            adapter_name="mcp_test_tool",
            hitl_required=False,
        )
        assert manifest.context_key == CONTEXT_DOMAIN_MCP

    def test_hitl_required_set(self):
        discovered = MCPDiscoveredTool(
            server_name="test",
            tool_name="tool",
            description="A test tool",
        )
        manifest = _mcp_tool_to_manifest(
            discovered=discovered,
            adapter_name="mcp_test_tool",
            hitl_required=True,
        )
        assert manifest.permissions.hitl_required is True

    def test_parameters_converted(self):
        discovered = MCPDiscoveredTool(
            server_name="test",
            tool_name="tool",
            description="A tool",
            input_schema={
                "properties": {
                    "name": {"type": "string", "description": "Name"},
                    "count": {"type": "integer", "description": "Count"},
                },
                "required": ["name"],
            },
        )
        manifest = _mcp_tool_to_manifest(
            discovered=discovered,
            adapter_name="mcp_test_tool",
            hitl_required=False,
        )
        assert len(manifest.parameters) == 2
        name_param = next(p for p in manifest.parameters if p.name == "name")
        assert name_param.required is True
        assert name_param.type == "string"

    def test_semantic_keywords(self):
        discovered = MCPDiscoveredTool(
            server_name="database",
            tool_name="query",
            description="Execute SQL query on database",
        )
        manifest = _mcp_tool_to_manifest(
            discovered=discovered,
            adapter_name="mcp_database_query",
            hitl_required=False,
        )
        assert "database" in manifest.semantic_keywords
        assert "query" in manifest.semantic_keywords

    def test_display_metadata(self):
        discovered = MCPDiscoveredTool(
            server_name="test",
            tool_name="tool",
            description="Test",
        )
        manifest = _mcp_tool_to_manifest(
            discovered=discovered,
            adapter_name="mcp_test_tool",
            hitl_required=False,
        )
        assert manifest.display is not None
        assert manifest.display.i18n_key == "mcp_tool"
        assert manifest.display.category == "tool"


class TestJsonSchemaToParameters:
    """Test JSON Schema → ParameterSchema conversion."""

    def test_string_type(self):
        params = _json_schema_to_parameters(
            properties={"name": {"type": "string", "description": "Name"}},
            required=["name"],
        )
        assert len(params) == 1
        assert params[0].name == "name"
        assert params[0].type == "string"
        assert params[0].required is True

    def test_integer_type(self):
        params = _json_schema_to_parameters(
            properties={"count": {"type": "integer", "description": "Count"}},
            required=[],
        )
        assert params[0].type == "integer"
        assert params[0].required is False

    def test_unknown_type_defaults_to_string(self):
        params = _json_schema_to_parameters(
            properties={"unknown": {"type": "custom_type", "description": "Unknown"}},
            required=[],
        )
        assert params[0].type == "string"

    def test_empty_properties(self):
        params = _json_schema_to_parameters(properties={}, required=[])
        assert params == []


class TestCompactJsonSchema:
    """Test JSON Schema compaction for LLM prompt injection."""

    def test_simple_string_type(self):
        result = _compact_json_schema({"type": "string"})
        assert result == {"type": "string"}

    def test_enum_preserved(self):
        result = _compact_json_schema({"type": "string", "enum": ["a", "b", "c"]})
        assert result == {"type": "string", "enum": ["a", "b", "c"]}

    def test_format_preserved(self):
        result = _compact_json_schema({"type": "string", "format": "date-time"})
        assert result == {"type": "string", "format": "date-time"}

    def test_verbose_fields_stripped(self):
        """title, $schema, additionalProperties, default must be stripped."""
        result = _compact_json_schema(
            {
                "type": "string",
                "title": "My Title",
                "$schema": "http://json-schema.org/draft-07/schema#",
                "additionalProperties": False,
                "default": "foo",
                "description": "A description",
            }
        )
        assert result == {"type": "string"}

    def test_array_with_items(self):
        result = _compact_json_schema(
            {
                "type": "array",
                "items": {"type": "string", "enum": ["x", "y"]},
            }
        )
        assert result == {"type": "array", "items": {"type": "string", "enum": ["x", "y"]}}

    def test_object_with_properties(self):
        result = _compact_json_schema(
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "age": {"type": "integer"},
                },
                "required": ["name"],
            }
        )
        assert result == {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name"],
        }

    def test_any_of_union(self):
        result = _compact_json_schema(
            {
                "anyOf": [{"type": "string"}, {"type": "integer"}],
            }
        )
        assert result == {"anyOf": [{"type": "string"}, {"type": "integer"}]}

    def test_one_of_union(self):
        result = _compact_json_schema(
            {
                "oneOf": [{"type": "string"}, {"type": "null"}],
            }
        )
        assert result == {"oneOf": [{"type": "string"}, {"type": "null"}]}

    def test_depth_5_nested_object(self):
        """5 levels deep should be fully preserved (Excalidraw-like schema)."""
        schema = {
            "type": "array",  # depth 0
            "items": {
                "type": "object",  # depth 1
                "properties": {
                    "style": {
                        "type": "object",  # depth 2
                        "properties": {
                            "stroke": {
                                "type": "object",  # depth 3
                                "properties": {
                                    "color": {
                                        "type": "object",  # depth 4
                                        "properties": {
                                            "r": {"type": "integer"},  # depth 5
                                            "g": {"type": "integer"},
                                        },
                                        "required": ["r", "g"],
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }
        result = _compact_json_schema(schema)
        # All 5 levels should be preserved
        assert result is not None
        color = result["items"]["properties"]["style"]["properties"]["stroke"]["properties"][
            "color"
        ]
        assert color["type"] == "object"
        assert "r" in color["properties"]
        assert color["required"] == ["r", "g"]

    def test_depth_6_returns_fallback(self):
        """Level 6+ should hit the depth limit and return fallback type."""
        schema = {
            "type": "object",  # depth 0
            "properties": {
                "a": {
                    "type": "object",  # depth 1
                    "properties": {
                        "b": {
                            "type": "object",  # depth 2
                            "properties": {
                                "c": {
                                    "type": "object",  # depth 3
                                    "properties": {
                                        "d": {
                                            "type": "object",  # depth 4
                                            "properties": {
                                                "e": {
                                                    "type": "object",  # depth 5
                                                    "properties": {
                                                        "f": {
                                                            "type": "string",  # depth 6 - cut
                                                        },
                                                    },
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }
        result = _compact_json_schema(schema)
        assert result is not None
        # Navigate to depth 5
        e = result["properties"]["a"]["properties"]["b"]["properties"]["c"]["properties"]["d"][
            "properties"
        ]["e"]
        # Depth 5 object: properties recurse at depth 6, which returns None → fallback
        assert e["type"] == "object"
        assert e["properties"]["f"] == {"type": "string"}

    def test_empty_spec_returns_none(self):
        result = _compact_json_schema({})
        assert result is None

    def test_non_dict_returns_none(self):
        result = _compact_json_schema("not a dict")  # type: ignore[arg-type]
        assert result is None

    def test_complex_array_schema_populates_parameter(self):
        """json_schema_to_parameters should populate schema field for array types."""
        params = _json_schema_to_parameters(
            properties={
                "elements": {
                    "type": "array",
                    "description": "Drawing elements",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["rectangle", "ellipse"]},
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                        },
                        "required": ["type", "x", "y"],
                    },
                },
            },
            required=["elements"],
        )
        assert len(params) == 1
        assert params[0].name == "elements"
        assert params[0].type == "array"
        assert params[0].schema is not None
        assert params[0].schema["type"] == "array"
        assert "items" in params[0].schema
        assert params[0].schema["items"]["properties"]["type"]["enum"] == [
            "rectangle",
            "ellipse",
        ]

    def test_simple_string_no_schema_populated(self):
        """Simple string params should NOT get a schema field (no noise)."""
        params = _json_schema_to_parameters(
            properties={"name": {"type": "string", "description": "Name"}},
            required=["name"],
        )
        assert params[0].schema is None


class TestRegisterMcpTools:
    """Test dual-registry registration."""

    def test_register_creates_single_agent_manifest(self):
        """Only one AgentManifest should be created for all MCP tools."""
        mock_registry = MagicMock()

        discovered = {
            "server1": [
                MCPDiscoveredTool(
                    server_name="server1",
                    tool_name="tool_a",
                    description="Tool A",
                ),
                MCPDiscoveredTool(
                    server_name="server1",
                    tool_name="tool_b",
                    description="Tool B",
                ),
            ],
        }

        adapters = {
            "mcp_server1_tool_a": MCPToolAdapter.from_mcp_tool("server1", "tool_a", "Tool A", {}),
            "mcp_server1_tool_b": MCPToolAdapter.from_mcp_tool("server1", "tool_b", "Tool B", {}),
        }

        server_configs = {
            "server1": MCPServerConfig(
                transport=MCPTransportType.STDIO,
                command="npx",
            ),
        }

        with patch("src.domains.agents.tools.tool_registry.register_external_tool"):
            count = register_mcp_tools(
                registry=mock_registry,
                discovered_tools=discovered,
                adapters=adapters,
                server_configs=server_configs,
                global_hitl_required=True,
            )

        assert count == 2
        # One agent manifest
        mock_registry.register_agent_manifest.assert_called_once()
        # Two tool manifests
        assert mock_registry.register_tool_manifest.call_count == 2
        # Two tool instances
        assert mock_registry.register_tool_instance.call_count == 2

    def test_register_no_tools(self):
        mock_registry = MagicMock()
        count = register_mcp_tools(
            registry=mock_registry,
            discovered_tools={},
            adapters={},
            server_configs={},
            global_hitl_required=True,
        )
        assert count == 0
        mock_registry.register_agent_manifest.assert_not_called()

    def test_register_calls_central_registry(self):
        """Each tool must be registered in the central tool_registry."""
        mock_registry = MagicMock()

        discovered = {
            "server1": [
                MCPDiscoveredTool(
                    server_name="server1",
                    tool_name="tool_a",
                    description="Tool A",
                ),
            ],
        }

        adapter = MCPToolAdapter.from_mcp_tool("server1", "tool_a", "Tool A", {})
        adapters = {"mcp_server1_tool_a": adapter}

        server_configs = {
            "server1": MCPServerConfig(
                transport=MCPTransportType.STDIO,
                command="npx",
            ),
        }

        with patch(
            "src.domains.agents.tools.tool_registry.register_external_tool"
        ) as mock_register:
            register_mcp_tools(
                registry=mock_registry,
                discovered_tools=discovered,
                adapters=adapters,
                server_configs=server_configs,
                global_hitl_required=True,
            )

        mock_register.assert_called_once_with(adapter)
