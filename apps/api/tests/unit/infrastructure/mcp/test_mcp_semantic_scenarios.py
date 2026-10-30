"""Offline MCP contract scenarios: SDK payloads, real references and strict servers.

The server oracle reads the original JSON Schema through jsonschema, independently
of LIA's reductions. No model choice is mocked or counted as autonomous reasoning.
"""

import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from mcp.types import CallToolResult, Tool

from src.core.context import (
    UserMCPToolsContext,
    get_request_tool_manifests,
    request_tool_manifests_ctx,
    user_mcp_tools_ctx,
)
from src.domains.agents.orchestration.condition_evaluator import ReferenceResolver
from src.domains.agents.orchestration.jinja_evaluator import JinjaTemplateEvaluator
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.react_tool_wrapper import compose_tool_message, extract_data_block
from src.infrastructure.mcp.registration import build_mcp_tool_manifest
from src.infrastructure.mcp.semantic_schema import output_fields_from_schema, semantic_type_of
from src.infrastructure.mcp.tool_adapter import MCPToolAdapter, build_args_schema
from src.infrastructure.mcp.user_context import (
    _build_user_tool_manifest,
    _register_user_iterative_server,
)
from src.infrastructure.mcp.user_pool import PoolEntry
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter
from src.infrastructure.mcp.utils import structured_result_text


def _validator(schema):
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _manifest(tool):
    return build_mcp_tool_manifest(
        adapter_name=f"mcp_contract_{tool.name}",
        agent_name="mcp_contract_agent",
        tool_name=tool.name,
        description=tool.description or "Offline contract scenario",
        input_schema=tool.input_schema,
        output_schema=tool.output_schema,
        semantic_keywords=[],
        hitl_required=False,
    )


def test_late_allof_and_reference_siblings_keep_constraints_and_semantics():
    contract = {
        "type": "object",
        "$defs": {"Text": {"type": "string"}},
        "properties": {
            "address": {"allOf": [{"type": "string"}, {"format": "email", "minLength": 8}]},
            "mode": {"$ref": "#/$defs/Text", "enum": ["exact", "fuzzy"]},
        },
        "required": ["address", "mode"],
    }
    tool = Tool(name="lookup", input_schema=contract)
    schema = build_args_schema(tool.input_schema).model_json_schema()
    manifest = _manifest(tool)
    assert manifest.parameters[0].semantic_type == "email_address"
    assert _validator(schema).is_valid({"address": "ada@example.com", "mode": "exact"})
    assert not _validator(schema).is_valid({"address": "bad", "mode": "exact"})
    assert not _validator(schema).is_valid({"address": "ada@example.com", "mode": "other"})


def test_root_allof_publishes_every_required_argument():
    contract = {
        "type": "object",
        "allOf": [
            {"properties": {"query": {"type": "string"}}, "required": ["query"]},
            {"properties": {"limit": {"type": "integer", "maximum": 2}}, "required": ["limit"]},
        ],
    }
    tool = Tool(name="list", input_schema=contract)
    model = build_args_schema(contract)
    assert model is not None
    schema = model.model_json_schema()
    assert set(schema["properties"]) == {"query", "limit"}
    assert set(schema["required"]) == {"query", "limit"}
    assert {p.name for p in _manifest(tool).parameters if p.required} == {"query", "limit"}
    assert not _validator(schema).is_valid({"query": "Ada", "limit": 3})


def test_allof_keeps_parent_fields_and_late_hints_without_inventing_conflicted_types():
    contract = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
        "allOf": [
            {
                "properties": {
                    "id": {"allOf": [{"type": "string"}, {"x-semantic-type": "contact_id"}]}
                },
                "required": ["id"],
            }
        ],
    }
    manifest = _manifest(Tool(name="find", input_schema=contract))
    assert {p.name for p in manifest.parameters} == {"query", "id"}
    assert next(p for p in manifest.parameters if p.name == "id").semantic_type == "contact_id"
    assert (
        semantic_type_of(
            {
                "allOf": [
                    {"type": "string", "x-semantic-type": "contact_id"},
                    {"type": "string", "x-semantic-type": "calendar_event_id"},
                ]
            },
            {},
        )
        is None
    )


def test_constant_and_scalar_union_constraints_reach_both_execution_modes():
    contract = {
        "type": "object",
        "properties": {
            "version": {"const": "v2"},
            "key": {"anyOf": [{"type": "string", "format": "email"}, {"type": "integer"}]},
        },
        "required": ["version", "key"],
    }
    model = build_args_schema(contract)
    emitted = model.model_json_schema()
    assert _validator(emitted).is_valid({"version": "v2", "key": 3})
    assert not _validator(emitted).is_valid({"version": "v1", "key": 3})
    parameters = {
        p.name: p for p in _manifest(Tool(name="search", input_schema=contract)).parameters
    }
    assert parameters["key"].schema["anyOf"][1] == {"type": "integer"}
    assert [(c.kind, c.value) for c in parameters["version"].constraints] == [("enum", ["v2"])]


def test_actual_openai_tool_converter_preserves_nullable_nested_and_late_constraints():
    from langchain_core.utils.function_calling import convert_to_openai_function

    contract = {
        "type": "object",
        "properties": {
            "cursor": {"type": ["string", "null"]},
            "recipient": {"allOf": [{"type": "string"}, {"format": "email", "minLength": 8}]},
            "keys": {"type": "array", "items": {"type": ["string", "null"]}},
        },
        "required": ["cursor", "recipient", "keys"],
    }
    adapter = MCPToolAdapter.from_mcp_tool("strict", "send", "Offline contract", contract)
    emitted = convert_to_openai_function(adapter)["parameters"]
    arguments = {"cursor": None, "recipient": "ada@example.com", "keys": [None, "known"]}
    assert _validator(contract).is_valid(arguments)
    assert _validator(emitted).is_valid(arguments)
    assert not _validator(emitted).is_valid({**arguments, "recipient": "bad"})
    assert adapter.args_schema.model_validate(arguments).model_dump(by_alias=True) == arguments


@pytest.mark.parametrize(
    "value_schema",
    [
        {"anyOf": [{"type": "string", "format": "email"}, {"type": "integer"}]},
        {"type": ["string", "integer", "null"]},
        {"enum": ["pending", 3, None]},
    ],
)
def test_union_admits_valid_branches_without_coercing_the_wire_value(value_schema):
    contract = {"type": "object", "properties": {"value": value_schema}, "required": ["value"]}
    model = build_args_schema(contract)
    for value in ("ada@example.com", "pending", 3, None):
        arguments = {"value": value}
        if _validator(contract).is_valid(arguments):
            validated = model.model_validate(arguments).model_dump(by_alias=True)
            assert validated == arguments
            assert _validator(model.model_json_schema()).is_valid(arguments)
    assert semantic_type_of(value_schema, contract) is None


def test_nested_bounds_nullable_items_and_closed_object_survive_publication():
    contract = {
        "type": "object",
        "properties": {
            "filter": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "age": {"type": "integer", "minimum": 18, "maximum": 90},
                    "tags": {"type": "array", "items": {"type": ["string", "null"]}},
                },
                "required": ["age", "tags"],
            }
        },
        "required": ["filter"],
    }
    schema = build_args_schema(contract).model_json_schema()
    good = {"filter": {"age": 30, "tags": ["known", None]}}
    assert _validator(contract).is_valid(good)
    assert _validator(schema).is_valid(good)
    for invalid in (
        {"filter": {"age": 12, "tags": []}},
        {"filter": {"age": 30, "tags": [], "surprise": True}},
    ):
        assert not _validator(contract).is_valid(invalid)
        assert not _validator(schema).is_valid(invalid)


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["admin", "user"])
async def test_required_nullable_argument_reaches_a_strict_server(scope):
    contract = {
        "type": "object",
        "properties": {"cursor": {"type": ["string", "null"]}},
        "required": ["cursor"],
    }
    received = []

    async def call_tool(*args, **kwargs):
        arguments = kwargs.get("arguments", args[-1] if args else None)
        _validator(contract).validate(arguments)
        received.append(arguments)
        return structured_result_text(CallToolResult(content=[], structured_content={"ok": True}))

    if scope == "admin":
        adapter = MCPToolAdapter.from_mcp_tool("strict", "list", "", contract)
        target = "src.infrastructure.mcp.client_manager.get_mcp_client_manager"
    else:
        adapter = UserMCPToolAdapter.from_discovered_tool(
            UUID(int=1), UUID(int=2), "Strict", "list", "", contract
        )
        target = "src.infrastructure.mcp.user_pool.get_user_mcp_pool"
    arguments = adapter.args_schema.model_validate({"cursor": None}).model_dump(by_alias=True)
    with patch(target, return_value=SimpleNamespace(call_tool=call_tool)):
        result = await adapter._call_server(**arguments)
    assert received == [{"cursor": None}]
    assert result.structured_data["result"] == {"ok": True}


def test_leading_underscore_arguments_are_callable_through_wire_aliases():
    contract = {
        "type": "object",
        "properties": {"_account": {"type": "string"}, "json": {"type": "string"}},
        "required": ["_account", "json"],
    }
    model = build_args_schema(contract)
    arguments = {"_account": "acct-one", "json": "literal"}
    assert model.model_validate(arguments).model_dump(by_alias=True) == arguments
    assert set(model.model_json_schema()["required"]) == set(arguments)


def test_schema_paths_resolve_real_rank_two_payload_and_absent_keys_fail_honestly():
    schema = {
        "type": "object",
        "properties": {
            "groups": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "string", "format": "email"}},
            },
            "optional": {"type": "string", "format": "uri"},
        },
        "required": ["groups"],
    }
    payload = {"groups": [["ada@example.com"], ["bob@example.com"]]}
    _validator(schema).validate(payload)
    fields = {f.path: f for f in output_fields_from_schema(schema)}
    assert fields["result.groups"].semantic_type is None
    assert fields["result.groups[][]"].semantic_type == "email_address"
    resolver = ReferenceResolver()
    assert (
        resolver.resolve("$steps.lookup.result.groups[1][0]", {"lookup": {"result": payload}})
        == "bob@example.com"
    )
    assert fields["result.optional"].nullable
    with pytest.raises(KeyError):
        resolver.resolve("$steps.lookup.result.optional", {"lookup": {"result": payload}})


def test_output_union_publishes_only_common_bridges_resolvable_in_every_valid_variant():
    schema = {
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "kind": {"const": "person"},
                    "email": {"type": "string", "format": "email"},
                    "person_id": {"type": "string", "x-semantic-type": "contact_id"},
                },
                "required": ["kind", "email", "person_id"],
            },
            {
                "type": "object",
                "properties": {
                    "kind": {"const": "team"},
                    "email": {"type": "string", "format": "email"},
                    "team_id": {"type": "string"},
                },
                "required": ["kind", "email", "team_id"],
            },
        ]
    }
    fields = {field.path: field for field in output_fields_from_schema(schema)}
    assert set(fields) == {"result", "result.kind", "result.email"}
    assert fields["result.email"].semantic_type == "email_address"
    assert not fields["result.email"].nullable
    for payload in (
        {"kind": "person", "email": "ada@example.com", "person_id": "people/ada"},
        {"kind": "team", "email": "team@example.com", "team_id": "team/one"},
    ):
        _validator(schema).validate(payload)
        assert (
            ReferenceResolver().resolve(
                "$steps.lookup.result.email", {"lookup": {"result": payload}}
            )
            == payload["email"]
        )


@pytest.mark.asyncio
async def test_request_accounts_keep_discovered_types_and_sdk_payloads_isolated():
    calls = []

    async def call_tool(
        *, user_id, server_id, tool_name, arguments, timeout_seconds, built_from, declaration
    ):
        calls.append((user_id.int, server_id, tool_name, arguments))
        return structured_result_text(
            CallToolResult(
                content=[], structured_content={"email": f"person{user_id.int}@example.com"}
            )
        )

    async def request(account_number):
        user_id, server_id = UUID(int=account_number), UUID(
            f"{account_number:08x}-0000-0000-0000-000000000001"
        )
        tool = Tool(
            name="people",
            input_schema={"type": "object"},
            output_schema={
                "type": "object",
                "properties": {"email": {"type": "string", "format": "email"}},
            },
        )
        adapter = UserMCPToolAdapter.from_discovered_tool(
            server_id, user_id, "People", tool.name, "", tool.input_schema
        )
        manifest = _build_user_tool_manifest(
            adapter_name=adapter.name,
            tool_name=tool.name,
            description="Offline account scenario",
            input_schema=tool.input_schema,
            output_schema=tool.output_schema,
            server_name="People",
            server_domain="mcp_people",
            hitl_required=False,
        )
        user_token = user_mcp_tools_ctx.set(
            UserMCPToolsContext(tool_manifests=[manifest], tool_instances={adapter.name: adapter})
        )
        manifest_token = request_tool_manifests_ctx.set([manifest])
        try:
            await asyncio.sleep(0)
            result = await adapter._call_server()
            selected = get_request_tool_manifests()
            assert selected == [manifest]
            assert user_mcp_tools_ctx.get().tool_instances[adapter.name].user_id == user_id
            email = ReferenceResolver().resolve(
                "$steps.lookup.result.email", {"lookup": result.structured_data}
            )
            return selected[0].name, email
        finally:
            request_tool_manifests_ctx.reset(manifest_token)
            user_mcp_tools_ctx.reset(user_token)

    with patch(
        "src.infrastructure.mcp.user_pool.get_user_mcp_pool",
        return_value=SimpleNamespace(call_tool=call_tool),
    ):
        results = await asyncio.gather(request(1), request(2))
    assert results == [
        ("mcp_user_00000001_people", "person1@example.com"),
        ("mcp_user_00000002_people", "person2@example.com"),
    ]
    assert {entry[0] for entry in calls} == {1, 2}


def test_iterative_individual_contracts_stay_available_only_to_bound_react_tools():
    from src.domains.user_mcp.models import UserMCPServer

    user_id, server_id = UUID(int=1), UUID(int=2)
    server = UserMCPServer(
        id=server_id,
        user_id=user_id,
        name="People",
        url="https://example.com/mcp",
        auth_type="bearer",
        timeout_seconds=30,
        domain_description="People directory",
    )
    tool = Tool(
        name="people",
        description="List people",
        input_schema={"type": "object"},
        output_schema={
            "type": "object",
            "properties": {"email": {"type": "string", "format": "email"}},
        },
    )
    entry = PoolEntry(
        user_id=user_id,
        server_id=server_id,
        last_used=0,
        tools=[
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "output_schema": tool.output_schema,
            }
        ],
    )
    ctx = UserMCPToolsContext(server_domains={"People": "mcp_people"})
    _register_user_iterative_server(server, entry, user_id, ctx, False, {})
    name = "mcp_user_00000000_people"
    assert name in ctx.tool_instances and name in ctx.reactive_tool_manifests
    assert name not in {manifest.name for manifest in ctx.tool_manifests}
    assert len(ctx.tool_manifests) == 1 and ctx.tool_manifests[0].name.endswith("_task")
    outputs = {field.path: field for field in ctx.reactive_tool_manifests[name].outputs}
    assert outputs["result.email"].semantic_type == "email_address"


def test_react_matrix_projection_keeps_exact_source_indices_and_all_collection_counts():
    payload = {
        "groups": [[{"id": "one", "notes": "a" * 800}], [{"id": "two", "notes": "b" * 800}]],
        "other": [{"id": "three"}],
    }
    original = copy.deepcopy(payload)
    result = UnifiedToolOutput(
        message="Three matches",
        structured_data={"result": payload},
        metadata={"mcp_result_projection": True},
    )
    full = extract_data_block(result, 10000)
    view = json.loads(full.text)
    assert view["mcp_row_counts"] == {
        "result.groups[0]": 1,
        "result.groups[1]": 1,
        "result.other": 1,
    }
    assert [row["item"]["id"] for row in view["mcp_rows"]] == ["one", "two", "three"]
    assert "groups" not in view.get("result", {})
    resolver = ReferenceResolver()
    for row in view["mcp_rows"]:
        reference = f"$steps.lookup.{row['source_path']}[{row['source_index']}].id"
        assert resolver.resolve(reference, {"lookup": {"result": payload}}) == row["item"]["id"]
    cut = extract_data_block(result, 50)
    assert cut.truncated and cut.shown == 1 and cut.total == 3
    assert payload == original


def test_pipeline_jinja_uses_full_result_after_model_projection_and_strict_validation():
    payload = {
        "people": [{"email": f"person{i}@example.com", "notes": "a" * 900} for i in range(50)]
    }
    original = copy.deepcopy(payload)
    result = UnifiedToolOutput(
        message="50 matches",
        structured_data={"result": payload},
        metadata={"mcp_result_projection": True},
    )
    block = extract_data_block(result, 180)
    assert block.truncated and block.shown < 50
    projected = json.loads(block.text)
    assert projected["mcp_row_counts"] == {"result.people": 50}
    assert projected["mcp_rows"][0]["source_index"] == 0
    assert payload == original
    reference = "{{ steps.lookup.result.people[49].email }}"
    arguments = JinjaTemplateEvaluator().evaluate_parameters(
        {"recipient": reference}, {"lookup": result.structured_data}, "send"
    )
    assert (
        ReferenceResolver().resolve(
            "$steps.lookup.result.people[49].email", {"lookup": result.structured_data}
        )
        == arguments["recipient"]
    )
    strict_contract = {
        "type": "object",
        "properties": {"recipient": {"type": "string", "format": "email"}},
        "required": ["recipient"],
    }
    model = build_args_schema(strict_contract)
    validated = model.model_validate(arguments).model_dump(by_alias=True)
    _validator(strict_contract).validate(validated)
    assert validated == {"recipient": "person49@example.com"}
    message = compose_tool_message(result, tool_name="mcp_contract_people", budget_tokens=180)
    assert "</external_content>" in message
    assert message.rfind("</external_content>") < message.find("[Budget]")
    assert "source_path and source_index" in message
    assert "complete in the registry" not in message
