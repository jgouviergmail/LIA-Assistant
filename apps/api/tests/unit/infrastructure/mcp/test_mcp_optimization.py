"""Behavioral oracles for schema freshness, cache coherence and usable formats."""

import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_google_genai._function_utils import convert_to_genai_function_declarations

from src.core.config import settings
from src.domains.agents.services.react_tool_selector import bound_tool_tokens
from src.domains.agents.services.tool_embeddings_envelope import (
    read_server_cache,
    wrap_server_cache,
)
from src.domains.agents.utils.token_utils import count_tokens
from src.infrastructure.mcp.auth import MCPOAuth2Auth, MCPStaticTokenAuth
from src.infrastructure.mcp.catalogue_fingerprint import connection_fingerprint
from src.infrastructure.mcp.semantic_observations import semantic_observation_data
from src.infrastructure.mcp.tool_adapter import MCPToolAdapter
from src.infrastructure.mcp.user_pool import UserMCPClientPool
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter


def _pool():
    pool = UserMCPClientPool()
    pool._raise_if_cooling = AsyncMock()
    pool._discover_tools = AsyncMock(
        return_value=(
            [
                {
                    "name": "find",
                    "description": "Find",
                    "input_schema": {"properties": {"query": {"type": "string"}}},
                }
            ],
            None,
        )
    )
    return pool


@pytest.mark.asyncio
async def test_hot_account_refreshes_schema_age_while_another_account_stays_current(monkeypatch):
    monkeypatch.setattr(settings, "mcp_user_pool_ttl_seconds", 60)
    clock = [100.0]
    monkeypatch.setattr("src.infrastructure.mcp.user_pool.time.monotonic", lambda: clock[0])
    pool = _pool()
    first = await pool.get_or_connect(UUID(int=1), UUID(int=2), "https://example.com", None)
    clock[0] = 130
    other = await pool.get_or_connect(UUID(int=3), UUID(int=2), "https://example.com", None)
    first.last_used = 159
    pool._discover_tools.return_value = (
        [
            {
                "name": "find",
                "description": "Find",
                "input_schema": {"properties": {"filter": {"type": "object"}}},
            }
        ],
        None,
    )
    clock[0] = 161
    new = await pool.get_or_connect(UUID(int=1), UUID(int=2), "https://example.com", None)
    unchanged = await pool.get_or_connect(UUID(int=3), UUID(int=2), "https://example.com", None)
    assert "filter" in new.tools[0]["input_schema"]["properties"]
    assert new.catalogue_fingerprint != first.catalogue_fingerprint
    assert unchanged is other and "query" in other.tools[0]["input_schema"]["properties"]
    assert pool._discover_tools.await_count == 3
    assert "query" in first.tools[0]["input_schema"]["properties"]  # in-flight snapshot immutable


@pytest.mark.asyncio
async def test_effective_connection_configuration_change_refreshes_same_account():
    pool = _pool()
    first = await pool.get_or_connect(
        UUID(int=1), UUID(int=2), "https://example.com", None, extra_headers={"X-View": "one"}
    )
    new = await pool.get_or_connect(
        UUID(int=1),
        UUID(int=2),
        "https://example.com",
        None,
        timeout_seconds=45,
        extra_headers={"X-View": "two"},
    )
    assert new is not first and new.timeout_seconds == 45
    assert pool._discover_tools.await_count == 2


@pytest.mark.asyncio
async def test_changed_static_auth_refreshes_catalogue_without_exporting_secret():
    pool = _pool()
    first = await pool.get_or_connect(
        UUID(int=1), UUID(int=2), "https://example.com", MCPStaticTokenAuth("X-Key", "secret-one")
    )
    unchanged = await pool.get_or_connect(
        UUID(int=1), UUID(int=2), "https://example.com", MCPStaticTokenAuth("X-Key", "secret-one")
    )
    changed = await pool.get_or_connect(
        UUID(int=1), UUID(int=2), "https://example.com", MCPStaticTokenAuth("X-Key", "secret-two")
    )
    assert unchanged is first and changed is not first and pool._discover_tools.await_count == 2
    assert "secret-" not in changed.configuration_fingerprint


def test_oauth_identity_tracks_scope_without_fetching_rotating_tokens():
    get_credentials = AsyncMock()
    arguments = {
        "server_id": UUID(int=1),
        "get_creds_fn": get_credentials,
        "update_creds_fn": AsyncMock(),
        "mark_auth_required_fn": AsyncMock(),
        "token_endpoint": "https://example.com/token",
        "client_id": "app",
    }
    first = MCPOAuth2Auth(**arguments, catalogue_scope="read")
    same = MCPOAuth2Auth(**arguments, catalogue_scope="read")
    changed = MCPOAuth2Auth(**arguments, catalogue_scope="read write")

    def fingerprint(auth):
        return connection_fingerprint("https://example.com", auth, 30, None)

    assert fingerprint(first) == fingerprint(same) != fingerprint(changed)
    get_credentials.assert_not_called()


def test_token_cache_tracks_serialized_schema_even_when_name_is_identical():
    small = MCPToolAdapter.from_mcp_tool(
        "optimization", "find", "Find", {"properties": {"query": {"type": "string"}}}
    )
    large = MCPToolAdapter.from_mcp_tool(
        "optimization",
        "find",
        "Find",
        {"properties": {f"filter_{i}": {"type": "string"} for i in range(100)}},
    )
    before = bound_tool_tokens([small])
    after = bound_tool_tokens([large])
    oracle = count_tokens(json.dumps(convert_to_openai_tool(large), ensure_ascii=False))
    assert after == oracle and after > before * 10


def test_embedding_envelope_invalidates_metadata_but_not_dictionary_key_order():
    tools = [
        {
            "name": "find",
            "description": "Find email",
            "input_schema": {"properties": {"query": {"type": "string"}}},
        }
    ]
    vectors = {"find": {"description": [0.1, 0.2]}}
    cache = wrap_server_cache(vectors, tool_metadata=tools)
    assert read_server_cache(cache, tool_metadata=[dict(reversed(list(tools[0].items())))]) == (
        vectors,
        None,
    )
    changed = copy.deepcopy(tools)
    changed[0]["input_schema"]["properties"]["query"]["format"] = "email"
    assert read_server_cache(cache, tool_metadata=changed) == ({}, "catalogue_changed")


@pytest.mark.asyncio
async def test_invalid_known_format_is_nonusable_without_losing_received_result():
    schema = {
        "type": "object",
        "properties": {
            "people": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "email": {"type": "string", "format": "email"},
                        "id": {"type": "string"},
                    },
                    "required": ["email", "id"],
                },
            }
        },
    }
    payload = {
        "people": [
            {"email": "invalid", "id": "unknown-id"},
            {"email": "ada@example.com", "id": "unchanged"},
        ]
    }
    adapter = MCPToolAdapter.from_mcp_tool(
        "optimization", "people", "People", {}, output_schema=schema
    )
    manager = SimpleNamespace(call_tool=AsyncMock(return_value=json.dumps(payload)))
    with patch(
        "src.infrastructure.mcp.client_manager.get_mcp_client_manager", return_value=manager
    ):
        result = await adapter._call_server()
    assert result.structured_data["result"] == payload
    invalid = result.structured_data["mcp_semantic_observations"]["unusable_paths"]
    assert invalid == [
        {
            "path": "result.people[0].email",
            "semantic_type": "email_address",
            "reason": "invalid_format",
        }
    ]
    assert "invalid" not in result.message  # raw values never echoed in diagnostic prose


def test_google_projection_keeps_late_assertions_and_full_contract_visible():
    contract = {
        "properties": {
            "email": {"allOf": [{"type": "string"}, {"format": "email", "minLength": 8}]}
        },
        "required": ["email"],
    }
    adapter = MCPToolAdapter.from_mcp_tool("optimization", "send", "Send", contract)
    emitted = adapter.args_schema.model_json_schema()
    oracle = Draft202012Validator(emitted, format_checker=FormatChecker())
    assert oracle.is_valid({"email": "ada@example.com"}) and not oracle.is_valid({"email": "bad"})
    converted = convert_to_genai_function_declarations([adapter])
    tool = converted[0] if isinstance(converted, list) else converted
    google_field = (
        tool.function_declarations[0].parameters.properties["email"].model_dump(exclude_none=True)
    )
    # The installed converter has no faithful native assertion projection here.
    # The producer must nevertheless see the ORIGINAL contract, not a silent downgrade.
    description = google_field["description"]
    assert '"minLength":8' in description and '"format":"email"' in description


@pytest.mark.asyncio
async def test_refresh_replaces_metadata_while_inflight_call_owns_original_snapshot(monkeypatch):
    monkeypatch.setattr(settings, "mcp_user_pool_ttl_seconds", 60)
    pool = _pool()
    first = await pool.get_or_connect(UUID(int=1), UUID(int=2), "https://example.com", None)
    started, finish = asyncio.Event(), asyncio.Event()

    async def execute(**arguments):
        started.set()
        await finish.wait()
        return "unchanged in-flight result"

    pool._execute_call_ephemeral = execute
    task = asyncio.create_task(pool.call_tool(UUID(int=1), UUID(int=2), "find", {}))
    await started.wait()
    new = await pool.get_or_connect(
        UUID(int=1), UUID(int=2), "https://example.com", None, force_refresh=True
    )
    assert new is not first and first.active_calls == 1 and new.active_calls == 0
    finish.set()
    assert await task == "unchanged in-flight result" and first.active_calls == 0


@pytest.mark.asyncio
async def test_expired_refresh_failure_is_visible_and_never_rebrands_stale_metadata():
    pool = _pool()
    first = await pool.get_or_connect(UUID(int=1), UUID(int=2), "https://example.com", None)
    pool._discover_tools.side_effect = RuntimeError("discovery unavailable")
    with pytest.raises(RuntimeError, match="discovery unavailable"):
        await pool.get_or_connect(
            UUID(int=1), UUID(int=2), "https://example.com", None, force_refresh=True
        )
    assert pool._entries[(UUID(int=1), UUID(int=2))] is first
    assert first.catalogue_fingerprint and pool._discover_tools.await_count == 2


@pytest.mark.asyncio
async def test_concurrent_expired_requests_share_one_refresh(monkeypatch):
    monkeypatch.setattr(settings, "mcp_user_pool_ttl_seconds", 60)
    pool = _pool()
    first = await pool.get_or_connect(UUID(int=1), UUID(int=2), "https://example.com", None)
    first.discovered_at -= 61
    results = await asyncio.gather(
        *[
            pool.get_or_connect(UUID(int=1), UUID(int=2), "https://example.com", None)
            for _ in range(8)
        ]
    )
    assert all(entry is results[0] for entry in results) and results[0] is not first
    assert pool._discover_tools.await_count == 2


@pytest.mark.parametrize(
    ("format_name", "valid", "invalid"),
    [
        ("email", "ada@example.com", "not-an-email"),
        ("date", "2026-10-06", "2026-02-30"),
        ("date-time", "2026-10-06T10:11:12+02:00", "2026-10-06T10:11:12"),
        ("uri", "https://example.com/path", "https://example.com/bad%zz"),
    ],
)
def test_known_format_observations_are_exact_value_facts(format_name, valid, invalid):
    schema = {"type": "array", "items": {"type": "string", "format": format_name}}
    assert semantic_observation_data([valid], schema) == {}
    observation = semantic_observation_data([invalid, valid], schema)["mcp_semantic_observations"]
    assert observation["unusable_count"] == 1
    assert observation["unusable_paths"][0]["path"] == "result[0]"


def test_optional_is_not_nullable_and_untyped_ids_are_never_guessed():
    schema = {
        "type": "object",
        "properties": {
            "optional": {"type": "string", "format": "email"},
            "nullable": {"type": ["string", "null"], "format": "email"},
            "id": {"type": "string"},
        },
    }
    assert semantic_observation_data({}, schema) == {}
    observation = semantic_observation_data(
        {"optional": None, "nullable": None, "id": "not-an-email"}, schema
    )["mcp_semantic_observations"]
    assert observation["unusable_paths"] == [
        {"path": "result.optional", "semantic_type": "email_address", "reason": "invalid_type"}
    ]


def test_observation_sample_is_bounded_without_claiming_unexamined_rows_valid():
    schema = {"type": "array", "items": {"type": "string", "format": "email"}}
    observation = semantic_observation_data(["invalid"] * 100, schema)["mcp_semantic_observations"]
    assert observation["unusable_count"] == 100 and observation["paths_truncated"] is True
    assert len(observation["unusable_paths"]) == 64
    assert observation["unusable_paths"][-1]["path"] == "result[63]"


def test_later_union_branch_allows_null_on_common_declared_field():
    schema = {
        "anyOf": [
            {"type": "object", "properties": {"email": {"type": "string", "format": "email"}}},
            {
                "type": "object",
                "properties": {"email": {"type": ["string", "null"], "format": "email"}},
            },
        ]
    }
    assert Draft202012Validator(schema).is_valid({"email": None})
    assert semantic_observation_data({"email": None}, schema) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("app", [False, True])
async def test_user_adapter_and_app_publish_same_canonical_value_and_unusable_path(app):
    payload = {"email": "bad", "id": "unknown-id"}
    schema = {
        "type": "object",
        "properties": {"email": {"type": "string", "format": "email"}},
    }
    adapter = UserMCPToolAdapter.from_discovered_tool(
        UUID(int=1),
        UUID(int=2),
        "People",
        "people",
        "People",
        {},
        app_resource_uri="ui://people" if app else None,
        output_schema=schema,
    )
    pool = SimpleNamespace(
        call_tool=AsyncMock(return_value=json.dumps(payload)),
        read_resource=AsyncMock(return_value="<p>People</p>"),
    )
    with patch("src.infrastructure.mcp.user_pool.get_user_mcp_pool", return_value=pool):
        result = await adapter._call_server()
    assert result.structured_data["result"] == payload
    assert (
        result.structured_data["mcp_semantic_observations"]["unusable_paths"][0]["path"]
        == "result.email"
    )
    assert "unusable" in result.message
