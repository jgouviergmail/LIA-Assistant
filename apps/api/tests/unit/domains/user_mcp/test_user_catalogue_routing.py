"""Request catalogue oracles using the real pool, adapters and manifest factories."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from pydantic import JsonValue

from src.core.config import settings
from src.core.context import (
    UserMCPToolsContext,
    build_request_tool_manifests,
    request_tool_manifests_ctx,
    user_mcp_tools_ctx,
)
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.services.analysis.domain_availability import build_available_domains
from src.domains.agents.services.tool_embeddings_envelope import wrap_server_cache
from src.domains.user_mcp.models import UserMCPServer
from src.infrastructure.mcp.user_context import cleanup_user_mcp_tools, setup_user_mcp_tools
from src.infrastructure.mcp.user_pool import UserMCPClientPool


def _tool(name: str, description: str = "Search current records") -> dict[str, JsonValue]:
    return {"name": name, "description": description, "input_schema": {"type": "object"}}


def _assert_manifest_origins(ctx: UserMCPToolsContext, servers: list[UserMCPServer]) -> None:
    manifests = [*ctx.tool_manifests, *ctx.reactive_tool_manifests.values()]
    assert {m.agent.removesuffix("_agent") for m in manifests} == set(ctx.server_domains.values())
    assert {m.mcp_origin for m in manifests} == {"user"}
    assert {m.mcp_server_key for m in manifests} == {str(server.id) for server in servers}


def _routing_domains(ctx: UserMCPToolsContext) -> set[str]:
    user_token = user_mcp_tools_ctx.set(ctx)
    manifests_token = request_tool_manifests_ctx.set(build_request_tool_manifests(AgentRegistry()))
    try:
        return {
            item["name"] for item in build_available_domains() if item["name"].startswith("mcp")
        }
    finally:
        request_tool_manifests_ctx.reset(manifests_token)
        user_mcp_tools_ctx.reset(user_token)


@dataclass
class RoutingHarness:
    account_id: UUID = field(default_factory=uuid4)
    servers: list[UserMCPServer] = field(default_factory=list)
    discoveries: dict[str, list[dict[str, JsonValue]] | Exception] = field(default_factory=dict)
    clock: list[float] = field(default_factory=lambda: [1000.0])
    queried_accounts: list[UUID] = field(default_factory=list)
    compute_embeddings: AsyncMock = field(default_factory=lambda: AsyncMock(return_value={}))

    def server(
        self,
        name: str,
        tools: list[dict[str, JsonValue]],
        *,
        iterative: bool = False,
        description: str | None = None,
    ) -> UserMCPServer:
        server = UserMCPServer(
            id=uuid4(),
            user_id=self.account_id,
            name=name,
            url=f"https://server-{len(self.servers)}.example/mcp",
            auth_type="none",
            is_enabled=True,
            status="active",
            timeout_seconds=30,
            extra_headers=None,
            hitl_required=False,
            iterative_mode=iterative,
            domain_description=description,
            tool_embeddings_cache=wrap_server_cache({}, tool_metadata=tools),
        )
        self.servers.append(server)
        self.discoveries[server.url] = tools
        return server

    async def context(self) -> UserMCPToolsContext:
        token = await setup_user_mcp_tools(self.account_id)
        try:
            ctx = user_mcp_tools_ctx.get()
            assert token is not None and ctx is not None
            return ctx
        finally:
            cleanup_user_mcp_tools(token)


@pytest.fixture
def routing(monkeypatch: pytest.MonkeyPatch) -> RoutingHarness:
    harness = RoutingHarness()
    pool = UserMCPClientPool()

    async def discover(
        url: str,
        auth: object,
        timeout_seconds: int,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[list[dict[str, JsonValue]], None]:
        result = harness.discoveries[url]
        if isinstance(result, Exception):
            raise result
        return result, None

    async def not_cooling(key: tuple[UUID, UUID]) -> None:
        pass

    class Repository:
        def __init__(self, db: object) -> None:
            pass

        async def get_enabled_active_for_user(self, account_id: UUID) -> list[UserMCPServer]:
            harness.queried_accounts.append(account_id)
            return list(harness.servers)

        async def get_tool_embeddings_cache(self, server_id: UUID) -> dict[str, object] | None:
            # The envelope is read alone (ADR-283 amendment): the fake mirrors
            # the production contract and serves what the row carries.
            for server in harness.servers:
                if server.id == server_id:
                    return getattr(server, "tool_embeddings_cache", None)
            return None

    @asynccontextmanager
    async def session() -> AsyncIterator[object]:
        yield object()

    monkeypatch.setattr(settings, "mcp_user_enabled", True)
    monkeypatch.setattr(settings, "mcp_react_enabled", True)
    monkeypatch.setattr(settings, "mcp_user_pool_ttl_seconds", 60)
    monkeypatch.setattr(pool, "_discover_tools", discover)
    monkeypatch.setattr(pool, "_raise_if_cooling", not_cooling)
    monkeypatch.setattr("src.infrastructure.mcp.user_pool.time.monotonic", lambda: harness.clock[0])
    monkeypatch.setattr("src.infrastructure.mcp.user_context.get_user_mcp_pool", lambda: pool)
    monkeypatch.setattr("src.domains.user_mcp.repository.UserMCPServerRepository", Repository)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.mcp.user_context.get_admin_mcp_domains", lambda: {})
    monkeypatch.setattr("src.infrastructure.mcp.registration.get_admin_mcp_domains", lambda: {})
    monkeypatch.setattr(
        "src.infrastructure.mcp.registration.get_admin_mcp_server_domains", lambda: {}
    )
    monkeypatch.setattr(
        "src.domains.agents.services.tool_selector.compute_tool_embeddings",
        harness.compute_embeddings,
    )
    return harness


@pytest.mark.asyncio
async def test_failed_and_empty_servers_are_not_published(routing: RoutingHarness) -> None:
    healthy = routing.server("Healthy", [_tool("search")])
    failed = routing.server("Failed", [])
    routing.discoveries[failed.url] = RuntimeError("Unavailable")
    routing.server("Empty", [])
    ctx = await routing.context()
    assert ctx.server_domains == {healthy.name: "mcp_healthy"}
    assert set(ctx.server_descriptions) == {healthy.name}
    assert {m.agent for m in ctx.tool_manifests} == {"mcp_healthy_agent"}
    assert _routing_domains(ctx) == {"mcp_healthy"}
    assert routing.queried_accounts == [routing.account_id]
    routing.compute_embeddings.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("iterative", [False, True])
async def test_app_only_server_does_not_publish_a_domain_or_delegate(
    routing: RoutingHarness, iterative: bool
) -> None:
    healthy = routing.server("Healthy", [_tool("search")])
    app_tool = _tool("iframe_operation")
    app_tool["app_visibility"] = ["app"]
    hidden = routing.server("Iframe", [app_tool], iterative=iterative)
    ctx = await routing.context()
    assert ctx.server_domains == {healthy.name: "mcp_healthy"}
    assert not any(str(hidden.id)[:8] in name for name in ctx.tool_instances)


@pytest.mark.asyncio
@pytest.mark.parametrize("iterative", [False, True])
async def test_admin_reservations_and_user_collisions_reach_actual_manifests(
    routing: RoutingHarness, monkeypatch: pytest.MonkeyPatch, iterative: bool
) -> None:
    monkeypatch.setattr(
        "src.infrastructure.mcp.user_context.get_admin_mcp_domains", lambda: {"mcp_foo": "Admin"}
    )
    for name in ["foo", "foo!", "foo_2"]:
        routing.server(name, [_tool("search")], iterative=iterative)
    ctx = await routing.context()
    domains = set(ctx.server_domains.values())
    assert len(domains) == 3 and "mcp_foo" not in domains
    _assert_manifest_origins(ctx, routing.servers)
    assert _routing_domains(ctx) == domains


@pytest.mark.asyncio
@pytest.mark.parametrize("iterative", [False, True])
async def test_fresh_capabilities_survive_stored_description_and_schema_refresh(
    routing: RoutingHarness, iterative: bool
) -> None:
    custom = "Treasury production: use only approved records."
    server = routing.server(
        "Treasury",
        [_tool("search_v1", "Search old records")],
        iterative=iterative,
        description=custom,
    )
    before = await routing.context()
    assert "search_v1" in before.server_descriptions[server.name]
    routing.clock[0] += 61
    routing.discoveries[server.url] = [_tool("reconcile_v2", "Reconcile current invoices")]
    after = await routing.context()
    assert server.domain_description == custom
    assert after.server_descriptions[server.name].startswith(custom)
    assert "reconcile_v2" in after.server_descriptions[server.name]
    assert "search_v1" not in after.server_descriptions[server.name]
    assert (
        before.server_catalogue_fingerprints[server.name]
        != after.server_catalogue_fingerprints[server.name]
    )
    assert after.server_description_sources[server.name] == "stored+discovered"
    if iterative:
        task = after.tool_manifests[0]
        assert custom in task.description and "reconcile_v2" in task.description
        assert "reconcile_v2" in after.tool_instances[task.name].description


@pytest.mark.asyncio
async def test_schema_only_refresh_updates_manifest_and_fingerprint(
    routing: RoutingHarness,
) -> None:
    first = _tool("find", "Find records")
    first["input_schema"] = {
        "type": "object",
        "properties": {"value": {"type": "string", "format": "email"}},
    }
    server = routing.server("Directory", [first])
    before = await routing.context()
    changed = _tool("find", "Find records")
    changed["input_schema"] = {
        "type": "object",
        "properties": {"value": {"type": "string", "format": "date"}},
    }
    routing.discoveries[server.url] = [changed]
    routing.clock[0] += 61
    after = await routing.context()
    assert before.tool_manifests[0].parameters[0].semantic_type == "email_address"
    assert after.tool_manifests[0].parameters[0].semantic_type == "Date"
    assert (
        before.server_catalogue_fingerprints[server.name]
        != after.server_catalogue_fingerprints[server.name]
    )
    assert before.server_descriptions[server.name] == after.server_descriptions[server.name]
    assert after.server_description_sources[server.name] == "discovered"


@pytest.mark.asyncio
async def test_every_usable_tool_name_reaches_routing_description(routing: RoutingHarness) -> None:
    names = [f"search_topic_{i}" for i in range(6)] + ["create_invoice"]
    server = routing.server("Business", [_tool(name) for name in names])
    ctx = await routing.context()
    description = ctx.server_descriptions[server.name]
    assert all(name in description for name in names)
