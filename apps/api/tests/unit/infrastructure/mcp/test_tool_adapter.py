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

    def test_an_unresolvable_ref_keeps_the_property(self):
        """Was: ``None`` for the WHOLE tool as soon as one property used ``$ref``.

        Measured, that published the tool to the model as a single opaque
        ``kwargs`` object — no field names, no descriptions, no required list —
        so the model could not call it. And the MCP spec (2026-07-28) requires
        ``$ref`` to be accepted: refusing it is a conformance defect, not a
        conservative choice.
        """
        schema = {
            "properties": {
                "nested": {"$ref": "#/definitions/Nested", "description": "A nested thing"},
            },
            "required": [],
        }
        model = build_args_schema(schema)
        assert model is not None
        assert "nested" in model.model_fields
        assert model.model_json_schema()["properties"]["nested"]["description"] == "A nested thing"
        # Undecidable type => permissive validation; the server stays the authority.
        assert model(nested={"anything": 1}).nested == {"anything": 1}

    def test_a_resolvable_ref_is_typed_from_its_target(self):
        schema = {
            "$defs": {"Nested": {"type": "object", "properties": {"x": {"type": "integer"}}}},
            "properties": {"nested": {"$ref": "#/$defs/Nested"}},
            "required": ["nested"],
        }
        model = build_args_schema(schema)
        assert model is not None
        assert model.model_json_schema()["properties"]["nested"]["type"] == "object"

    def test_allof_is_reduced_not_refused(self):
        schema = {
            "properties": {
                "field": {"allOf": [{"type": "string"}, {"minLength": 1}]},
            },
            "required": [],
        }
        model = build_args_schema(schema)
        assert model is not None
        assert model.model_json_schema()["properties"]["field"]["anyOf"] == [
            {"type": "string"},
            {"type": "null"},
        ]

    def test_one_undecidable_property_does_not_cost_the_others(self):
        """The regression that made the fallback harmful: a single unreadable
        declaration used to erase every sibling's name and description."""
        schema = {
            "properties": {
                "opaque": {"not": {"type": "string"}},
                "query": {"type": "string", "description": "Search text"},
                "limit": {"type": "integer", "description": "Row limit"},
            },
            "required": ["query"],
        }
        model = build_args_schema(schema)
        assert model is not None
        props = model.model_json_schema()["properties"]
        assert set(props) == {"opaque", "query", "limit"}
        assert props["query"]["description"] == "Search text"
        assert model.model_json_schema()["required"] == ["query"]

    def test_a_leading_underscore_property_costs_only_itself(self):
        """``create_model`` refuses the name; it used to take the tool with it."""
        model = build_args_schema(
            {"properties": {"_internal": {"type": "string"}, "kept": {"type": "string"}}}
        )
        assert model is not None
        assert set(model.model_fields) == {"kept"}

    def test_a_schema_of_only_unusable_properties_still_degrades_to_none(self):
        assert build_args_schema({"properties": {"_a": {"type": "string"}}}) is None

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

    def test_args_schema_survives_a_complex_declaration(self):
        adapter = MCPToolAdapter.from_mcp_tool(
            server_name="test",
            tool_name="complex",
            description="Complex tool",
            input_schema={
                "properties": {"data": {"$ref": "#/defs/Data"}},
                "required": [],
            },
        )
        assert adapter.args_schema is not None
        assert "data" in adapter.args_schema.model_fields

    def test_the_model_is_never_shown_an_opaque_kwargs_object(self):
        """The oracle for the whole change, through the REAL provider converter.

        With ``args_schema=None`` LangChain publishes ``{"kwargs": {...}}``: the
        tool is listed but its signature is unknowable, so the model either
        skips it or calls it wrongly. Whatever a declaration contains, the
        parameter names must reach the model.
        """
        from langchain_core.utils.function_calling import convert_to_openai_tool

        adapter = MCPToolAdapter.from_mcp_tool(
            server_name="test",
            tool_name="mixed",
            description="Mixed tool",
            input_schema={
                "properties": {
                    "ref_field": {"$ref": "#/defs/Absent"},
                    "any_of_field": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                    "plain": {"type": "string", "description": "Plain"},
                },
                "required": ["plain"],
            },
        )
        params = convert_to_openai_tool(adapter)["function"]["parameters"]
        assert set(params["properties"]) == {"ref_field", "any_of_field", "plain"}
        assert "kwargs" not in params["properties"]
        assert params["required"] == ["plain"]


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


class TestUnionTypeSchemas:
    """``type`` declared as a LIST — legal JSON Schema, and what real servers emit.

    The MCP spec (2026-07-28) admits every JSON Schema 2020-12 keyword in a
    tool's ``inputSchema``. A list is unhashable, so keying a lookup on it
    raised ``TypeError`` and ``_register_user_iterative_server`` dropped the
    tool: prod 2026-09-01 lost 30 of one server's 40 tools, including the only
    one able to list the user's bank accounts.
    """

    def test_optional_union_becomes_a_typed_nullable_field(self):
        model = build_args_schema(
            {
                "properties": {"include_hidden": {"type": ["boolean", "null"], "default": False}},
                "required": [],
            }
        )
        assert model is not None
        field = model.model_json_schema()["properties"]["include_hidden"]
        assert field["anyOf"] == [{"type": "boolean"}, {"type": "null"}]
        assert field["default"] is False

    def test_required_union_stays_required_and_accepts_null(self):
        """The server said null is acceptable — we must not be stricter than it."""
        model = build_args_schema(
            {"properties": {"key": {"type": ["string", "null"]}}, "required": ["key"]}
        )
        assert model is not None
        assert model.model_fields["key"].is_required()
        assert model(key=None).key is None

    def test_required_non_nullable_union_rejects_null(self):
        model = build_args_schema(
            {"properties": {"key": {"type": ["string"]}}, "required": ["key"]}
        )
        assert model is not None
        with pytest.raises(ValueError):
            model(key=None)

    def test_union_array_keeps_its_declared_items(self):
        model = build_args_schema(
            {
                "properties": {
                    "rule_ids": {"type": ["array", "null"], "items": {"type": "string"}}
                },
                "required": [],
            }
        )
        assert model is not None
        props = model.model_json_schema()["properties"]
        assert _array_member(props["rule_ids"])["items"] == {"type": "string"}

    def test_union_inside_array_items(self):
        model = build_args_schema(
            {
                "properties": {"tags": {"type": "array", "items": {"type": ["string", "null"]}}},
                "required": [],
            }
        )
        assert model is not None
        props = model.model_json_schema()["properties"]
        assert _array_member(props["tags"])["items"] == {"type": "string"}

    def test_multi_concrete_union_still_accepts_every_member(self):
        """Pydantic's lax coercion means the narrowing rejects no valid call."""
        model = build_args_schema(
            {"properties": {"amount": {"type": ["number", "string"]}}, "required": []}
        )
        assert model is not None
        assert model(amount="3.5").amount == 3.5
        assert model(amount=7).amount == 7.0

    @pytest.mark.parametrize("declared", [["null"], [], ["date", "null"]])
    def test_undecidable_union_degrades_to_string(self, declared):
        model = build_args_schema({"properties": {"p": {"type": declared}}, "required": []})
        assert model is not None
        assert model.model_json_schema()["properties"]["p"]["anyOf"] == [
            {"type": "string"},
            {"type": "null"},
        ]

    @pytest.mark.parametrize("spec", ["string", None, 42, ["a"]])
    def test_a_malformed_property_spec_degrades_instead_of_killing_the_tool(self, spec):
        """A server may send junk; one bad property must not cost the whole tool."""
        model = build_args_schema(
            {"properties": {"p": spec, "sane": {"type": "string"}}, "required": []}
        )
        assert model is not None
        assert set(model.model_fields) == {"p", "sane"}

    def test_era_list_financial_accounts_regression(self):
        """The exact schema Era Context publishes — the tool the incident lost."""
        adapter = MCPToolAdapter.from_mcp_tool(
            server_name="era",
            tool_name="accounts__list_financial_accounts",
            description="List all linked bank accounts",
            input_schema={
                "type": "object",
                "properties": {
                    "include_hidden": {
                        "default": False,
                        "description": "Also show hidden accounts.",
                        "type": ["boolean", "null"],
                    }
                },
            },
        )
        assert adapter.args_schema is not None
        field = adapter.args_schema.model_json_schema()["properties"]["include_hidden"]
        assert field["description"] == "Also show hidden accounts."
        assert field["default"] is False

    def test_gemini_function_declaration_accepts_a_nullable_array(self):
        """Same oracle as the 2026-08-14 prod failure, on the union form."""
        from langchain_google_genai._function_utils import (
            convert_to_genai_function_declarations,
        )

        adapter = MCPToolAdapter.from_mcp_tool(
            server_name="era",
            tool_name="search",
            description="Search",
            input_schema={
                "properties": {
                    "rule_ids": {"type": ["array", "null"], "items": {"type": "string"}}
                },
                "required": [],
            },
        )
        out = convert_to_genai_function_declarations([adapter])
        tool = out[0] if isinstance(out, list) else out
        items = tool.function_declarations[0].parameters.properties["rule_ids"].items
        assert items is not None
        assert str(items.type) != "Type.TYPE_UNSPECIFIED"


class TestMalformedToolSchemas:
    """``build_args_schema`` reads a third-party payload: it must never raise."""

    @pytest.mark.parametrize("properties", [None, "junk", ["a"], 42])
    def test_non_dict_properties_degrade_to_no_schema(self, properties):
        assert build_args_schema({"properties": properties}) is None

    @pytest.mark.parametrize("required", [None, "abc", 42, {"a": 1}])
    def test_a_non_list_required_is_ignored(self, required):
        model = build_args_schema({"properties": {"a": {"type": "string"}}, "required": required})
        assert model is not None
        assert not model.model_fields["a"].is_required()

    def test_required_entries_that_are_not_names_are_ignored(self):
        model = build_args_schema(
            {"properties": {"a": {"type": "string"}}, "required": ["a", 3, None]}
        )
        assert model is not None
        assert model.model_fields["a"].is_required()


class TestConstraintsReachTheModel:
    """What the server enforces must reach whoever produces the value (ADR-184).

    An MCP tool published none of it: Era declares ``direction`` as a closed set
    of four values, and the model had to guess them from prose. A closed set the
    model cannot see is a trap, not a contract.
    """

    def test_an_enum_reaches_the_emitted_schema(self):
        model = build_args_schema(
            {
                "properties": {"sort_by": {"type": "string", "enum": ["date", "amount"]}},
                "required": ["sort_by"],
            }
        )
        assert model is not None
        assert model.model_json_schema()["properties"]["sort_by"]["enum"] == ["date", "amount"]

    def test_the_era_direction_enum_loses_only_its_null_member(self):
        """Era spells an optional enum with a null member and no ``type`` at all."""
        model = build_args_schema(
            {
                "properties": {
                    "direction": {
                        "default": "all",
                        "description": "Money direction.",
                        "enum": ["all", "debit", "credit", None],
                    }
                }
            }
        )
        assert model is not None
        field = model.model_json_schema()["properties"]["direction"]
        assert field["anyOf"] == [
            {"type": "string", "enum": ["all", "debit", "credit"]},
            {"type": "null"},
        ]
        assert field["default"] == "all"

    def test_numeric_bounds_reach_the_emitted_schema(self):
        model = build_args_schema(
            {"properties": {"limit": {"type": ["integer", "null"], "minimum": 1, "maximum": 50}}}
        )
        assert model is not None
        member = model.model_json_schema()["properties"]["limit"]["anyOf"][0]
        assert member == {"type": "integer", "minimum": 1, "maximum": 50}

    def test_publication_never_becomes_enforcement(self):
        """The MCP server is the authority on its own input: a value outside the
        advertised set must still travel, or we invent an error it never had."""
        model = build_args_schema({"properties": {"sort_by": {"type": "string", "enum": ["date"]}}})
        assert model is not None
        assert model(sort_by="merchant").sort_by == "merchant"

    def test_gemini_receives_the_enum_as_a_real_closed_set(self):
        from langchain_google_genai._function_utils import (
            convert_to_genai_function_declarations,
        )

        adapter = MCPToolAdapter.from_mcp_tool(
            server_name="era",
            tool_name="search",
            description="Search",
            input_schema={
                "properties": {"direction": {"type": "string", "enum": ["debit", "credit"]}},
                "required": ["direction"],
            },
        )
        out = convert_to_genai_function_declarations([adapter])
        tool = out[0] if isinstance(out, list) else out
        prop = tool.function_declarations[0].parameters.properties["direction"]
        assert list(prop.enum) == ["debit", "credit"]

    def test_an_unconstrained_field_emits_exactly_what_it_always_did(self):
        """Publication must not churn the declaration of a plain parameter."""
        model = build_args_schema(
            {"properties": {"q": {"type": "string", "description": "Query"}}, "required": ["q"]}
        )
        assert model is not None
        assert model.model_json_schema()["properties"]["q"] == {
            "type": "string",
            "description": "Query",
            "title": "Q",
        }


class TestConstraintsDoNotDisturbArgumentCoercion:
    """Publishing constraints wraps the type in ``Annotated``. That must stay
    invisible to ``parallel_executor._coerce_args_to_schema``, which branches on
    ``field.annotation is str``.

    Pydantic v2 strips the metadata and returns the bare type, so the branch
    still fires — but nothing in this codebase says so, and the day it stopped
    being true a planner writing a JSON object into a string parameter would
    silently stop being repaired. Hence this oracle.
    """

    @pytest.mark.parametrize(
        "spec",
        [
            {"type": "string"},
            {"type": "string", "enum": ["a", "b"]},
            {"type": "string", "maxLength": 10},
            {"type": "string", "pattern": "^x"},
        ],
    )
    def test_a_string_parameter_still_reports_a_bare_str_annotation(self, spec):
        from src.domains.agents.orchestration.parallel_executor import _coerce_args_to_schema

        model = build_args_schema({"properties": {"sql": spec}, "required": ["sql"]})
        assert model is not None
        assert model.model_fields["sql"].annotation is str
        # The repair the branch exists for (MCP FIX, Excalidraw elements).
        assert _coerce_args_to_schema({"sql": {"k": 1}}, model)["sql"] == '{"k": 1}'

    @pytest.mark.parametrize(
        "spec", [{"type": "integer"}, {"type": "integer", "minimum": 1, "maximum": 50}]
    )
    def test_an_integer_parameter_still_reports_a_bare_int_annotation(self, spec):
        from src.domains.agents.orchestration.parallel_executor import _coerce_args_to_schema

        model = build_args_schema({"properties": {"n": spec}, "required": ["n"]})
        assert model is not None
        assert model.model_fields["n"].annotation is int
        assert _coerce_args_to_schema({"n": 3.7}, model)["n"] == 3
