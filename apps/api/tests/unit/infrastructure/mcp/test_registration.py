"""
Unit tests for MCP registration bridge.

Tests dual-registry registration (AgentRegistry + tool_registry),
manifest generation, and JSON Schema parameter conversion.

Phase: evolution F2 — MCP Support
Created: 2026-02-28
"""

from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.constants import AGENT_MCP
from src.infrastructure.mcp.registration import (
    _compact_json_schema,
    _json_schema_to_parameters,
    _mcp_tool_to_manifest,
    build_mcp_adapters,
    build_mcp_tool_manifest,
    declared_tool_category,
    record_tool_registration_failure,
    register_mcp_tools,
)
from src.infrastructure.mcp.schemas import MCPDiscoveredTool, MCPServerConfig, MCPTransportType
from src.infrastructure.mcp.tool_adapter import MCPToolAdapter, build_args_schema


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

    def test_context_key_absent(self):
        """MCP manifests carry NO context_key — the claim was always false.

        "mcps" was never a registered context type (MCP result shapes are
        heterogeneous per server), so the wave auto-save error-logged
        "Context type 'mcps' not registered" on every MCP tool result once
        MCP-domain turns reached the pipeline (prod, 2026-07-21). A None
        context_key makes the executor skip the save cleanly (its designed
        no-context path) instead of attempting a doomed one.
        """
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
        assert manifest.context_key is None

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


class TestUnionTypeParameters:
    """The planner manifest must survive the same union declarations.

    Fixing only the adapter would have moved the crash, not removed it: in
    pipeline mode the caller builds the adapter AND the manifest inside one
    ``try``, so the tool disappeared either way.
    """

    @pytest.mark.parametrize(
        ("declared", "expected"),
        [
            (["string", "null"], "string"),
            (["boolean", "null"], "boolean"),
            (["integer", "null"], "integer"),
            (["array", "null"], "array"),
            (["object", "null"], "object"),
            (["null"], "string"),
            (["custom", "null"], "string"),
        ],
    )
    def test_union_type_is_normalized(self, declared, expected):
        params = _json_schema_to_parameters(
            properties={"p": {"type": declared, "description": "d"}}, required=[]
        )
        assert params[0].type == expected

    def test_nullable_array_keeps_its_items_in_the_manifest(self):
        """A union made ``param_type == "array"`` false, silently dropping items."""
        params = _json_schema_to_parameters(
            properties={"rule_ids": {"type": ["array", "null"], "items": {"type": "string"}}},
            required=[],
        )
        assert params[0].schema == {"type": "array", "items": {"type": "string"}}

    def test_nullable_object_keeps_its_properties_in_the_manifest(self):
        params = _json_schema_to_parameters(
            properties={
                "where": {
                    "type": ["object", "null"],
                    "properties": {"lat": {"type": ["number", "null"]}},
                }
            },
            required=[],
        )
        assert params[0].schema == {"type": "object", "properties": {"lat": {"type": "number"}}}

    @pytest.mark.parametrize("spec", ["string", None, 42])
    def test_a_malformed_property_spec_degrades_to_string(self, spec):
        params = _json_schema_to_parameters(properties={"p": spec}, required=[])
        assert params[0].type == "string"
        assert params[0].description == ""

    def test_compact_schema_normalizes_a_union(self):
        assert _compact_json_schema({"type": ["string", "null"], "format": "date"}) == {
            "type": "string",
            "format": "date",
        }


class TestMalformedServerSchemas:
    """A third-party server may send junk where a schema is expected.

    On the user paths a raised exception costs one tool; in ``register_mcp_tools``
    at boot the loop has no per-tool guard, so it costs every admin MCP tool.
    """

    def test_compact_schema_survives_non_dict_properties(self):
        assert _compact_json_schema({"type": "object", "properties": "junk"}) == {"type": "object"}

    def test_compact_schema_survives_non_dict_nested_property(self):
        assert _compact_json_schema({"type": "object", "properties": {"a": "junk"}}) == {
            "type": "object",
            "properties": {"a": {"type": "string"}},
        }

    @pytest.mark.parametrize("properties", [None, "junk", ["a"], 42])
    def test_manifest_survives_non_dict_properties(self, properties):
        manifest = build_mcp_tool_manifest(
            adapter_name="mcp_x_y",
            agent_name="mcp_x_agent",
            tool_name="y",
            description="d",
            input_schema={"properties": properties},
            semantic_keywords=[],
            hitl_required=True,
        )
        assert manifest.parameters == []

    @pytest.mark.parametrize("required", [None, "abc", 42])
    def test_manifest_survives_a_non_list_required(self, required):
        manifest = build_mcp_tool_manifest(
            adapter_name="mcp_x_y",
            agent_name="mcp_x_agent",
            tool_name="y",
            description="d",
            input_schema={"properties": {"a": {"type": "string"}}, "required": required},
            semantic_keywords=[],
            hitl_required=True,
        )
        assert [p.name for p in manifest.parameters] == ["a"]
        assert manifest.parameters[0].required is False


class TestBuildMcpAdapters:
    """One malformed admin tool must cost ITS tool, not every admin MCP tool.

    The per-user paths have caught per tool since F2.1; the admin boot loop ran
    inside ``init_mcp``'s single try/except, so one unbuildable declaration
    aborted ``register_mcp_tools`` entirely and the assistant lost every admin
    MCP capability behind one error line.
    """

    @staticmethod
    def _tool(name: str, schema: dict | None = None) -> MCPDiscoveredTool:
        return MCPDiscoveredTool(
            server_name="srv",
            tool_name=name,
            description=f"{name} description",
            input_schema=(
                schema if schema is not None else {"properties": {"a": {"type": "string"}}}
            ),
        )

    def test_every_buildable_tool_yields_one_adapter(self):
        adapters = build_mcp_adapters({"srv": [self._tool("alpha"), self._tool("beta")]})
        assert set(adapters) == {"mcp_srv_alpha", "mcp_srv_beta"}

    def test_a_union_typed_tool_builds(self):
        """Regression tie: this is the declaration that used to abort the boot."""
        adapters = build_mcp_adapters(
            {"srv": [self._tool("nullable", {"properties": {"a": {"type": ["string", "null"]}}})]}
        )
        assert adapters["mcp_srv_nullable"].args_schema is not None

    def test_an_unbuildable_tool_is_skipped_and_its_siblings_survive(self):
        real_factory = MCPToolAdapter.from_mcp_tool

        def _raise_for_bad(**kwargs):
            if kwargs["tool_name"] == "bad":
                raise RuntimeError("declaration we cannot adapt")
            return real_factory(**kwargs)

        tools = [self._tool("good"), self._tool("bad"), self._tool("also_good")]
        with patch(
            "src.infrastructure.mcp.registration.MCPToolAdapter.from_mcp_tool",
            side_effect=_raise_for_bad,
        ):
            adapters = build_mcp_adapters({"srv": tools})

        assert set(adapters) == {"mcp_srv_good", "mcp_srv_also_good"}

    def test_a_failing_server_does_not_stop_the_next_server(self):
        real_factory = MCPToolAdapter.from_mcp_tool

        def _raise_for_srv_a(**kwargs):
            if kwargs["server_name"] == "a":
                raise RuntimeError("boom")
            return real_factory(**kwargs)

        with patch(
            "src.infrastructure.mcp.registration.MCPToolAdapter.from_mcp_tool",
            side_effect=_raise_for_srv_a,
        ):
            adapters = build_mcp_adapters(
                {
                    "a": [MCPDiscoveredTool(server_name="a", tool_name="x", description="d")],
                    "b": [MCPDiscoveredTool(server_name="b", tool_name="y", description="d")],
                }
            )

        assert set(adapters) == {"mcp_b_y"}

    def test_no_tools_yields_no_adapters(self):
        assert build_mcp_adapters({}) == {}
        assert build_mcp_adapters({"srv": []}) == {}


class TestRecordToolRegistrationFailure:
    """A dropped tool is a capability the user silently loses — it must be visible.

    Production ran 72 h dropping 30 of one server's 40 tools on every turn. The
    only trace was a warning nobody queries: no counter existed, so no panel
    could show it and no alert could fire (ADR-148 class).
    """

    def test_it_counts_by_scope_and_error_type(self):
        with patch(
            "src.infrastructure.mcp.registration.mcp_tool_registration_failures_total"
        ) as counter:
            try:
                raise TypeError("unhashable type: 'list'")
            except TypeError as exc:
                record_tool_registration_failure(
                    scope="admin", server="srv", tool_name="t", exc=exc
                )
        counter.labels.assert_called_once_with(scope="admin", error_type="TypeError")
        counter.labels.return_value.inc.assert_called_once()

    def test_it_logs_one_event_carrying_the_identifying_detail(self):
        """Server and tool live in the LOG: a per-server label would grow one
        series per user per server, and the log has no cardinality budget."""
        with (
            patch("src.infrastructure.mcp.registration.mcp_tool_registration_failures_total"),
            patch("src.infrastructure.mcp.registration.logger") as mock_logger,
        ):
            try:
                raise ValueError("nope")
            except ValueError as exc:
                caught = exc
                record_tool_registration_failure(
                    scope="user_iterative",
                    server="server-uuid",
                    tool_name="accounts__list",
                    exc=exc,
                    user_id="user-uuid",
                )
        event, fields = mock_logger.warning.call_args[0][0], mock_logger.warning.call_args[1]
        assert event == "mcp_tool_registration_failed"
        assert fields["scope"] == "user_iterative"
        assert fields["server"] == "server-uuid"
        assert fields["tool_name"] == "accounts__list"
        assert fields["error_type"] == "ValueError"
        assert fields["user_id"] == "user-uuid"
        # THAT exception's traceback, not whichever one is ambient.
        assert fields["exc_info"] is caught

    def test_the_admin_builder_reports_through_it(self):
        real_factory = MCPToolAdapter.from_mcp_tool

        def _boom(**kwargs):
            if kwargs["tool_name"] == "bad":
                raise RuntimeError("nope")
            return real_factory(**kwargs)

        with (
            patch(
                "src.infrastructure.mcp.registration.MCPToolAdapter.from_mcp_tool",
                side_effect=_boom,
            ),
            patch(
                "src.infrastructure.mcp.registration.mcp_tool_registration_failures_total"
            ) as counter,
        ):
            build_mcp_adapters(
                {
                    "srv": [
                        MCPDiscoveredTool(server_name="srv", tool_name="bad", description="d"),
                        MCPDiscoveredTool(server_name="srv", tool_name="ok", description="d"),
                    ]
                }
            )
        counter.labels.assert_called_once_with(scope="admin", error_type="RuntimeError")


class TestAdapterAndManifestAgree:
    """One declaration, one reading.

    The planner catalogue and the tool signature are two readings of the same
    ``inputSchema``. They each had their own, and they disagreed: the adapter
    raised on a union while the manifest silently dropped the array items of
    the very same property. Both now go through ``resolve_property``, and this
    is the test that says so.
    """

    SCHEMAS: list[tuple[str, dict]] = [
        (
            "union",
            {"properties": {"p": {"type": ["string", "null"]}}},
        ),
        (
            "anyOf optional",
            {"properties": {"p": {"anyOf": [{"type": "integer"}, {"type": "null"}]}}},
        ),
        (
            "oneOf",
            {"properties": {"p": {"oneOf": [{"type": "boolean"}, {"type": "string"}]}}},
        ),
        (
            "allOf",
            {"properties": {"p": {"allOf": [{"type": "number"}, {"minimum": 0}]}}},
        ),
        (
            "ref into defs",
            {
                "$defs": {"T": {"type": "array", "items": {"type": "string"}}},
                "properties": {"p": {"$ref": "#/$defs/T"}},
            },
        ),
        (
            "const",
            {"properties": {"p": {"const": 7}}},
        ),
        (
            "enum with null",
            {"properties": {"p": {"enum": ["a", "b", None]}}},
        ),
    ]

    @pytest.mark.parametrize(("label", "schema"), SCHEMAS, ids=[s[0] for s in SCHEMAS])
    def test_the_manifest_type_matches_the_adapter_field(self, label, schema):
        manifest = build_mcp_tool_manifest(
            adapter_name="mcp_x_y",
            agent_name="mcp_x_agent",
            tool_name="y",
            description="d",
            input_schema=schema,
            semantic_keywords=[],
            hitl_required=True,
        )
        model = build_args_schema(schema)
        assert model is not None, label

        emitted = model.model_json_schema()["properties"]["p"]
        members = emitted.get("anyOf", [emitted])
        adapter_types = {m.get("type") for m in members if m.get("type") != "null"}

        assert manifest.parameters[0].name == "p"
        # Every declaration in this table IS decidable, so both readings must
        # name the same type. No escape hatch: a loose assertion here is exactly
        # how the two readings drifted apart in the first place.
        assert adapter_types != {None}, f"{label}: adapter failed to type a decidable schema"
        assert (
            manifest.parameters[0].type in adapter_types
        ), f"{label}: manifest={manifest.parameters[0].type} adapter={adapter_types}"

    def test_the_one_deliberate_asymmetry_is_the_undecidable_property(self):
        """A manifest parameter is typed ``str``: it must name a type even when
        there is none to name, and "string" is its historical fallback. The
        adapter can be honest instead, and validates permissively. The planner
        then proposes a string, which the adapter accepts — the asymmetry costs
        nothing, and is pinned here so it stays deliberate.
        """
        schema = {"properties": {"p": {"not": {"type": "string"}}}}
        manifest = build_mcp_tool_manifest(
            adapter_name="mcp_x_y",
            agent_name="mcp_x_agent",
            tool_name="y",
            description="d",
            input_schema=schema,
            semantic_keywords=[],
            hitl_required=True,
        )
        model = build_args_schema(schema)
        assert manifest.parameters[0].type == "string"
        assert model is not None
        emitted = model.model_json_schema()["properties"]["p"]
        # The empty member IS the honest answer: JSON Schema spells "any type"
        # as a schema with no constraint, not as "string".
        assert emitted["anyOf"] == [{}, {"type": "null"}]
        assert model(p={"an": "object"}).p == {"an": "object"}

    def test_a_referenced_array_shows_its_items_to_the_planner(self):
        """The manifest compacts the RESOLVED spec, not the $ref wrapper."""
        manifest = build_mcp_tool_manifest(
            adapter_name="mcp_x_y",
            agent_name="mcp_x_agent",
            tool_name="y",
            description="d",
            input_schema={
                "$defs": {"Tags": {"type": "array", "items": {"type": "string"}}},
                "properties": {"tags": {"$ref": "#/$defs/Tags"}},
            },
            semantic_keywords=[],
            hitl_required=True,
        )
        assert manifest.parameters[0].type == "array"
        assert manifest.parameters[0].schema == {"type": "array", "items": {"type": "string"}}

    def test_an_undecidable_property_is_still_offered_to_the_planner(self):
        params = _json_schema_to_parameters(
            properties={"opaque": {"not": {"type": "string"}}, "q": {"type": "string"}},
            required=["q"],
        )
        assert [p.name for p in params] == ["opaque", "q"]
        assert params[0].type == "string"


class TestManifestConstraints:
    """MCP parameters join the constraint machinery native tools already had.

    ``smart_catalogue_service`` renders ``enum``/``min``/``max`` to the planner
    from ``ParameterSchema.constraints``, ``parameter_bounds`` clamps out-of-range
    numbers from the same source, and MCP tools populated none of it.
    """

    @staticmethod
    def _params(schema: dict) -> list:
        return build_mcp_tool_manifest(
            adapter_name="mcp_x_y",
            agent_name="mcp_x_agent",
            tool_name="y",
            description="d",
            input_schema=schema,
            semantic_keywords=[],
            hitl_required=True,
        ).parameters

    def test_enum_and_bounds_become_catalogue_constraints(self):
        params = self._params(
            {
                "properties": {
                    "limit": {"type": ["integer", "null"], "minimum": 1, "maximum": 50},
                    "sort_by": {"enum": ["date", "amount", None]},
                }
            }
        )
        by_name = {p.name: {c.kind: c.value for c in p.constraints} for p in params}
        assert by_name["limit"] == {"minimum": 1, "maximum": 50}
        # The null member stays: this constraint is what the plan validator
        # checks against, and stripping it would reject a value the server
        # accepts (see TestNullableEnumSurvivesThePlanValidator).
        assert by_name["sort_by"] == {"enum": ["date", "amount", None]}

    def test_constraints_are_read_through_a_ref(self):
        params = self._params(
            {
                "$defs": {"Unit": {"type": "string", "enum": ["metric", "imperial"]}},
                "properties": {"unit": {"$ref": "#/$defs/Unit"}},
            }
        )
        assert [c.value for c in params[0].constraints if c.kind == "enum"] == [
            ["metric", "imperial"]
        ]

    def test_a_third_party_pattern_never_reaches_the_plan_validator(self):
        """The validator compiles constraint patterns with ``re.match`` on an
        async path: a catastrophic backtracker there freezes the event loop and
        every SSE stream, and no ``except`` interrupts it."""
        params = self._params({"properties": {"code": {"type": "string", "pattern": "^(a+)+$"}}})
        assert [c.kind for c in params[0].constraints] == []

    def test_an_unconstrained_parameter_declares_no_constraint(self):
        params = self._params({"properties": {"q": {"type": "string"}}})
        assert params[0].constraints == []


class TestDeclaredToolCategory:
    """Behaviour hints may TIGHTEN the classification, never loosen it.

    The spec is normative on this point:

        "For trust & safety and security, clients MUST consider tool
         annotations to be untrusted unless they come from trusted servers."

    So a declared ``destructiveHint`` is acted upon — the worst case is one
    confirmation too many — while a declared ``readOnlyHint: true`` is NOT,
    because acting on it would delete a tool from the mutation safety net and
    from HITL scope detection on the word of a third party.

    The gain is concrete: none of Era's ``cancel_subscription``, ``upgrade``,
    ``disconnect_institution`` or ``forget`` carries one of the nine mutation
    verbs, so the name heuristic calls them all read-only today.
    """

    @pytest.mark.parametrize(
        ("annotations", "expected"),
        [
            ({"destructive_hint": True}, "delete"),
            ({"read_only_hint": False}, "delete"),
            ({"read_only_hint": False, "destructive_hint": True}, "delete"),
            # Spec: destructiveHint false means the tool performs only additive updates.
            ({"read_only_hint": False, "destructive_hint": False}, "update"),
            # A contradiction resolves the safe way.
            ({"read_only_hint": True, "destructive_hint": True}, "delete"),
        ],
    )
    def test_a_declared_mutation_is_believed(self, annotations, expected):
        assert declared_tool_category(annotations) == expected

    @pytest.mark.parametrize(
        "annotations",
        [
            {"read_only_hint": True},
            {"destructive_hint": False},
            {"idempotent_hint": True, "open_world_hint": False},
            {"title": "Something"},
            {},
            None,
            "junk",
        ],
    )
    def test_nothing_usable_leaves_the_name_heuristic_in_charge(self, annotations):
        """None means "not declared" — the caller keeps its historical fallback."""
        assert declared_tool_category(annotations) is None

    def test_a_read_only_claim_never_relaxes_a_mutating_name(self):
        """THE regression guard for this whole lot.

        A server claiming read-only on a tool whose name says otherwise must not
        remove it from the safety net. ``declared_tool_category`` returning None
        is exactly what keeps ``tool_is_mutation`` on the name heuristic.
        """
        assert declared_tool_category({"read_only_hint": True}) is None

    def test_the_manifest_carries_the_declared_category(self):
        manifest = build_mcp_tool_manifest(
            adapter_name="mcp_era_billing__cancel_subscription",
            agent_name="mcp_era_agent",
            tool_name="billing__cancel_subscription",
            description="Cancel the subscription",
            input_schema={"properties": {"reason": {"type": "string"}}},
            semantic_keywords=[],
            hitl_required=True,
            annotations={"read_only_hint": False, "destructive_hint": True},
        )
        assert manifest.tool_category == "delete"

    def test_without_annotations_the_manifest_stays_undeclared(self):
        """Unchanged behaviour for every server that publishes no hints."""
        manifest = build_mcp_tool_manifest(
            adapter_name="mcp_x_y",
            agent_name="mcp_x_agent",
            tool_name="y",
            description="d",
            input_schema={},
            semantic_keywords=[],
            hitl_required=True,
        )
        assert manifest.tool_category is None

    def test_a_declared_mutation_is_seen_by_the_mutation_predicate(self):
        """End to end: the classification must reach the safety net that reads it."""
        from src.domains.agents.orchestration.plan_predicates import tool_is_mutation
        from src.domains.agents.registry.catalogue import is_read_only_tool

        manifest = build_mcp_tool_manifest(
            adapter_name="mcp_era_knowledge__forget",
            agent_name="mcp_era_agent",
            tool_name="knowledge__forget",
            description="Forget a stored fact",
            input_schema={},
            semantic_keywords=[],
            hitl_required=True,
            annotations={"destructive_hint": True},
        )
        assert is_read_only_tool(manifest) is False

        registry = MagicMock()
        registry.get_tool_manifest.return_value = manifest
        with patch("src.domains.agents.registry.get_global_registry", return_value=registry):
            # "forget" carries none of the nine mutation verbs.
            assert tool_is_mutation("mcp_era_knowledge__forget") is True


class TestAnnotationsTravelFromDiscovery:
    """The hints must survive discovery, the schema and the manifest builder.

    Both registration paths go through ``build_mcp_tool_manifest``, so the
    derivation has one implementation — but each path has to actually hand it
    the hints, and a field nobody forwards is a field that does nothing.
    """

    def test_the_admin_path_carries_the_declared_category(self):
        discovered = MCPDiscoveredTool(
            server_name="era",
            tool_name="knowledge__forget",
            description="Forget a stored fact",
            annotations={"destructive_hint": True},
        )
        manifest = _mcp_tool_to_manifest(
            discovered=discovered,
            adapter_name="mcp_era_knowledge__forget",
            hitl_required=True,
        )
        assert manifest.tool_category == "delete"

    def test_the_admin_path_without_hints_is_unchanged(self):
        discovered = MCPDiscoveredTool(
            server_name="era", tool_name="list", description="List things"
        )
        manifest = _mcp_tool_to_manifest(
            discovered=discovered, adapter_name="mcp_era_list", hitl_required=True
        )
        assert manifest.tool_category is None

    def test_a_discovered_tool_keeps_its_title_and_hints(self):
        discovered = MCPDiscoveredTool(
            server_name="era",
            tool_name="accounts__list_financial_accounts",
            description="d",
            title="Financial accounts",
            annotations={"read_only_hint": True},
        )
        assert discovered.title == "Financial accounts"
        assert discovered.annotations == {"read_only_hint": True}

    def test_the_discovered_tool_defaults_leave_both_absent(self):
        discovered = MCPDiscoveredTool(server_name="s", tool_name="t", description="d")
        assert discovered.title is None
        assert discovered.annotations is None
