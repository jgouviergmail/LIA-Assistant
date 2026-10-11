"""MCP declarations create usable bridges only when the server states the type."""

import json
from collections import deque
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from mcp.types import CallToolResult, TextContent, Tool

from src.infrastructure.mcp.client_manager import MCPClientManager
from src.infrastructure.mcp.registration import build_mcp_tool_manifest, json_schema_to_parameters
from src.infrastructure.mcp.semantic_schema import output_fields_from_schema, semantic_type_of
from src.infrastructure.mcp.tool_adapter import MCPToolAdapter, build_args_schema
from src.infrastructure.mcp.user_context import _build_user_tool_manifest
from src.infrastructure.mcp.user_pool import UserMCPClientPool
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter
from src.infrastructure.mcp.utils import extract_output_schema, structured_result_text


@pytest.mark.parametrize(
    ("format_name", "expected"),
    [("email", "email_address"), ("uri", "URL"), ("date-time", "datetime"), ("date", "Date")],
)
def test_declared_formats_reach_native_semantic_parameters(format_name, expected):
    params = json_schema_to_parameters({"value": {"type": "string", "format": format_name}}, [])
    assert params[0].semantic_type == expected


@pytest.mark.parametrize("name", ["id", "address", "email", "query", "url"])
def test_a_suggestive_name_without_a_declaration_is_not_a_bridge(name):
    assert json_schema_to_parameters({name: {"type": "string"}}, [])[0].semantic_type is None


@pytest.mark.parametrize("hint", ["invented_type", "Email_Address", [], {"type": "contact_id"}])
def test_unknown_or_malformed_semantic_hints_never_enter_the_registry(hint):
    assert semantic_type_of({"type": "string", "x-semantic-type": hint}, {}) is None


def test_explicit_known_hints_and_local_reference_formats_are_resolved():
    root = {"$defs": {"Email": {"type": "string", "format": "email"}}}
    assert semantic_type_of({"$ref": "#/$defs/Email"}, root) == "email_address"
    assert semantic_type_of({"type": "string", "semantic_type": "contact_id"}, {}) == "contact_id"
    assert semantic_type_of({"type": "string", "x-semantic-type": "contact_id"}, {}) == "contact_id"


def test_a_heterogeneous_union_does_not_borrow_its_first_branch_semantics():
    spec = {"anyOf": [{"type": "string", "format": "email"}, {"type": "integer"}]}
    assert semantic_type_of(spec, {}) is None
    nullable = {"anyOf": [{"type": "string", "format": "email"}, {"type": "null"}]}
    assert semantic_type_of(nullable, {}) == "email_address"
    assert semantic_type_of({"type": ["string", "integer"], "format": "email"}, {}) is None
    root = {"$defs": {"Mixed": spec}}
    assert semantic_type_of({"$ref": "#/$defs/Mixed"}, root) is None


def test_array_object_items_and_reference_leaves_reach_planner_and_react_identically():
    root = {
        "$defs": {"Email": {"type": "string", "format": "email"}},
        "properties": {
            "attendees": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"email": {"$ref": "#/$defs/Email"}},
                    "required": ["email"],
                },
            }
        },
        "required": ["attendees"],
    }
    params = json_schema_to_parameters(root["properties"], root["required"], root=root)
    model = build_args_schema(root)
    assert model is not None
    planner = params[0].schema["items"]
    react = model.model_json_schema()["properties"]["attendees"]["items"]
    assert (
        planner
        == react
        == {
            "type": "object",
            "properties": {
                "email": {"type": "string", "format": "email", "x-semantic-type": "email_address"}
            },
            "required": ["email"],
        }
    )
    # The server remains the authority on its own validation.
    assert model(attendees=[{"other": 7}]).attendees == [{"other": 7}]
    assert params[0].semantic_type is None  # An attendee OBJECT is not an email address.


OUTPUT_SCHEMA = {
    "type": "object",
    "$defs": {"Email": {"type": "string", "format": "email"}},
    "properties": {
        "people": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "email": {"$ref": "#/$defs/Email"},
                    "id": {"type": "string"},
                    "profile": {"type": "string", "format": "uri"},
                },
                "required": ["email", "id"],
            },
        }
    },
    "required": ["people"],
}
PAYLOAD = {
    "people": [{"email": "ada@example.com", "id": "7", "profile": "https://example.com/ada"}]
}


def test_real_sdk_output_schema_and_catalogue_leaf_paths_agree():
    tool = Tool(name="people", input_schema={"type": "object"}, output_schema=OUTPUT_SCHEMA)
    assert extract_output_schema(tool) == OUTPUT_SCHEMA
    manifest = build_mcp_tool_manifest(
        adapter_name="mcp_people",
        agent_name="mcp_agent",
        tool_name="people",
        description="Find people",
        input_schema=tool.input_schema,
        output_schema=extract_output_schema(tool),
        semantic_keywords=[],
        hitl_required=False,
    )
    outputs = {field.path: field for field in manifest.outputs}
    assert outputs["result"].type == "object"
    assert outputs["result.people[].email"].semantic_type == "email_address"
    assert outputs["result.people[].id"].semantic_type is None
    assert outputs["result.people[].profile"].semantic_type == "URL"
    assert outputs["result.people[].profile"].nullable


def test_user_manifest_preserves_the_same_output_contract():
    manifest = _build_user_tool_manifest(
        adapter_name="mcp_user_x_people",
        tool_name="people",
        description="Find people",
        input_schema={},
        output_schema=OUTPUT_SCHEMA,
        server_name="People",
        server_domain="mcp_people",
        hitl_required=False,
    )
    assert manifest.outputs == output_fields_from_schema(OUTPUT_SCHEMA)


def test_an_absent_output_contract_stays_unknown():
    outputs = output_fields_from_schema(None)
    assert [(f.path, f.type, f.semantic_type) for f in outputs] == [("result", "any", None)]


def test_output_keys_outside_the_execution_dsl_are_not_advertised_as_paths():
    fields = output_fields_from_schema(
        {
            "type": "object",
            "properties": {
                "café": {"type": "string", "format": "email"},
                "full-name": {"type": "string"},
                "email": {"type": "string", "format": "email"},
            },
        }
    )
    assert [field.path for field in fields] == ["result", "result.email"]


def test_recursive_or_remote_references_do_not_fabricate_output_types():
    recursive = {
        "type": "object",
        "$defs": {"Loop": {"$ref": "#/$defs/Loop"}},
        "properties": {
            "item": {"$ref": "#/$defs/Loop"},
            "remote": {"$ref": "https://example.com/schema"},
        },
    }
    fields = output_fields_from_schema(recursive)
    assert fields[1].type == fields[2].type == "any"
    assert all(field.semantic_type is None for field in fields)


@pytest.mark.asyncio
async def test_admin_sdk_structured_content_survives_into_the_declared_paths():
    manager = MCPClientManager()
    response = CallToolResult(
        content=[TextContent(type="text", text="One person")], structured_content=PAYLOAD
    )
    manager._sessions["people"] = SimpleNamespace(call_tool=AsyncMock(return_value=response))
    manager._call_timestamps["people"] = deque()
    raw = await manager.call_tool("people", "people", {})
    assert json.loads(raw) == PAYLOAD
    adapter = MCPToolAdapter.from_mcp_tool("people", "people", "", {})
    with patch(
        "src.infrastructure.mcp.client_manager.get_mcp_client_manager", return_value=manager
    ):
        result = await adapter._call_server()
    assert result.structured_data["result"]["people"][0]["email"] == "ada@example.com"
    assert result.structured_data["mcp_text"] == "One person"
    from src.domains.agents.tools.react_tool_wrapper import mark_untrusted_data

    assert "<external_content" in mark_untrusted_data(result, json.dumps(result.structured_data))


@pytest.mark.asyncio
async def test_user_ephemeral_sdk_structured_content_and_adapter_paths_are_preserved():
    client = SimpleNamespace(
        call_tool=AsyncMock(return_value=CallToolResult(content=[], structured_content=PAYLOAD))
    )

    @asynccontextmanager
    async def ephemeral(*args):
        yield client

    with patch("src.infrastructure.mcp.user_pool._ephemeral_client", ephemeral):
        raw = await UserMCPClientPool()._execute_call_ephemeral(
            "https://example.com", None, "people", {}, 30
        )
    assert json.loads(raw) == PAYLOAD
    pool = SimpleNamespace(call_tool=AsyncMock(return_value=raw))
    adapter = UserMCPToolAdapter.from_discovered_tool(uuid4(), uuid4(), "People", "people", "", {})
    with patch("src.infrastructure.mcp.user_pool.get_user_mcp_pool", return_value=pool):
        result = await adapter._call_server()
    assert result.structured_data["result"] == PAYLOAD
    assert result.structured_data["people"][0]["email"] == PAYLOAD["people"][0]["email"]
    from src.domains.agents.tools.react_tool_wrapper import mark_untrusted_data

    assert "<external_content" in mark_untrusted_data(result, json.dumps(result.structured_data))


@pytest.mark.asyncio
async def test_both_discovery_paths_preserve_the_sdk_output_contract():
    tool = Tool(
        name="people",
        description="Find people",
        input_schema={"type": "object"},
        output_schema=OUTPUT_SCHEMA,
    )
    session = SimpleNamespace(list_tools=AsyncMock(return_value=SimpleNamespace(tools=[tool])))
    manager = MCPClientManager()
    manager._sessions["people"] = session
    discovered = await manager.discover_tools("people")
    assert discovered[0].output_schema == OUTPUT_SCHEMA

    @asynccontextmanager
    async def ephemeral(*args):
        yield session

    with patch("src.infrastructure.mcp.user_pool._ephemeral_client", ephemeral):
        user_tools, _ = await UserMCPClientPool._discover_tools("https://example.com", None, 30)
    assert user_tools[0]["output_schema"] == OUTPUT_SCHEMA


def test_alternative_result_shapes_do_not_advertise_phantom_leaf_paths():
    schema = {
        "anyOf": [
            {"type": "object", "properties": {"email": {"type": "string", "format": "email"}}},
            {"type": "object", "properties": {"phone": {"type": "string"}}},
        ]
    }
    fields = output_fields_from_schema(schema)
    assert [(field.path, field.semantic_type) for field in fields] == [("result", None)]
    mixed = output_fields_from_schema({"type": ["string", "object"]})
    assert mixed[0].type == "any"


def test_nested_input_object_alternatives_are_kept_on_both_prompt_surfaces():
    root = {
        "properties": {
            "selector": {
                "anyOf": [
                    {
                        "type": "object",
                        "properties": {"email": {"type": "string", "format": "email"}},
                    },
                    {"type": "object", "properties": {"name": {"type": "string"}}},
                ]
            }
        },
        "required": ["selector"],
    }
    parameter = json_schema_to_parameters(root["properties"], root["required"], root=root)[0]
    model = build_args_schema(root)
    assert model is not None
    signature = model.model_json_schema()["properties"]["selector"]
    assert signature["anyOf"] == parameter.schema["anyOf"]
    assert signature["anyOf"][0]["properties"]["email"]["x-semantic-type"] == "email_address"
    assert "email" not in signature["anyOf"][1]["properties"]
    assert model(selector={"name": "Ada"}).selector == {"name": "Ada"}
    assert parameter.semantic_type is None


@pytest.mark.parametrize(
    "hint",
    ["email_address", "contact_id", "datetime", "physical_address", "person_name", "phone_number"],
)
def test_scalar_hints_do_not_label_arrays_of_objects(hint):
    schema = {"type": "array", "items": {"type": "object"}, "x-semantic-type": hint}
    assert semantic_type_of(schema, schema) is None


def test_nested_arrays_keep_leaf_semantics_without_claiming_a_scalar_at_the_outer_container():
    schema = {
        "type": "array",
        "items": {"type": "array", "items": {"type": "string", "format": "email"}},
    }
    assert semantic_type_of(schema, schema) is None
    outputs = output_fields_from_schema(schema)
    assert outputs[0].semantic_type is None
    assert outputs[1].semantic_type == outputs[2].semantic_type == "email_address"
    assert outputs[2].path == "result[][]"


def test_optional_parent_collections_make_even_required_leaf_paths_nullable():
    schema = {
        "type": "object",
        "properties": {
            "people": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"email": {"type": "string", "format": "email"}},
                    "required": ["email"],
                },
            }
        },
    }
    outputs = output_fields_from_schema(schema)
    assert all(field.nullable for field in outputs if field.path != "result")


@pytest.mark.asyncio
async def test_large_nested_mcp_results_page_whole_rows_without_touching_jinja_data():
    from src.domains.agents.tools.react_tool_wrapper import extract_data_block

    payload = {
        "data": {
            "people": [{"email": f"person{i}@example.com", "bio": "x " * 80} for i in range(100)]
        },
        "next": None,
    }
    manager = SimpleNamespace(call_tool=AsyncMock(return_value=json.dumps(payload)))
    adapter = MCPToolAdapter.from_mcp_tool("people", "people", "Find people", {})
    with patch(
        "src.infrastructure.mcp.client_manager.get_mcp_client_manager", return_value=manager
    ):
        result = await adapter._call_server()
    block = extract_data_block(result, budget_tokens=200)
    assert block is not None and block.truncated
    view = json.loads(block.text)
    assert view["mcp_row_counts"] == {"result.data.people": 100}
    assert 1 <= block.shown < 100
    assert len(view["mcp_rows"]) == block.shown
    assert view["mcp_rows"][0] == {
        "source_path": "result.data.people",
        "source_index": 0,
        "item": payload["data"]["people"][0],
    }
    assert view["result"]["next"] is None
    assert result.structured_data["result"] == payload


@pytest.mark.asyncio
async def test_structured_data_keeps_auxiliary_server_caveats_and_deduplicates_json_copy():
    from src.domains.agents.tools.react_tool_wrapper import compose_tool_message

    caveat = "Only the first page was returned; fetch page 2 to complete the list."
    sdk_result = CallToolResult(
        content=[
            TextContent(type="text", text=json.dumps(PAYLOAD)),
            TextContent(type="text", text=caveat),
        ],
        structured_content=PAYLOAD,
    )
    raw = structured_result_text(sdk_result)
    assert isinstance(raw, str) and json.loads(raw) == PAYLOAD
    pool = SimpleNamespace(call_tool=AsyncMock(return_value=raw))
    adapter = UserMCPToolAdapter.from_discovered_tool(
        uuid4(), uuid4(), "People", "people", "Find people", {}
    )
    with patch("src.infrastructure.mcp.user_pool.get_user_mcp_pool", return_value=pool):
        result = await adapter._call_server()
    assert result.structured_data["mcp_text"] == caveat
    assert result.structured_data["result"] == PAYLOAD
    message = compose_tool_message(result, tool_name=adapter.name, budget_tokens=1000)
    assert caveat in message
    assert message.count("ada@example.com") == 1
    assert "<external_content" in message


@pytest.mark.asyncio
async def test_user_result_alias_never_overwrites_the_schema_root_and_is_not_dumped_twice():
    from src.domains.agents.tools.react_tool_wrapper import extract_data_block

    payload = {
        "result": [{"email": f"person{i}@example.com", "body": "x " * 30} for i in range(100)]
    }
    pool = SimpleNamespace(call_tool=AsyncMock(return_value=json.dumps(payload)))
    adapter = UserMCPToolAdapter.from_discovered_tool(
        uuid4(), uuid4(), "People", "people", "Find people", {}
    )
    with patch("src.infrastructure.mcp.user_pool.get_user_mcp_pool", return_value=pool):
        result = await adapter._call_server()
    assert result.structured_data["result"] == payload
    display_key = result.metadata["mcp_display_collection_key"]
    assert display_key != "result"
    block = extract_data_block(result, budget_tokens=200)
    assert block is not None and block.truncated and block.total == 100
    view = json.loads(block.text)
    assert display_key not in view
    assert view["mcp_row_counts"] == {"result.result": 100}
    assert len(view["mcp_rows"]) < 100
    assert "_registry_id" in view["mcp_rows"][0]["item"]
    assert result.structured_data["result"] == payload
