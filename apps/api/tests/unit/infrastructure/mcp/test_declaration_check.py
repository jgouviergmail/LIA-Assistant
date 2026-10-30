"""A tool served from an unverified catalogue is checked against its CURRENT declaration first.

Spec 2026-10-21 §5.5 (M3). A turn may serve a catalogue past the server's own
``ttlMs`` (Q1): the declaration the planner or the loop built the call from
may have changed since. Before such a call, the same ephemeral session lists
the tools and reads the called tool's current declaration:

- missing → refused (``missing``); arguments no longer valid → refused
  (``incompatible``); newly destructive → refused (``tightened``) — the call is
  NEVER sent, nothing retries it, and the model reads a structured ``CONFLICT``;
- a compatible difference sends the call and schedules a revalidation;
- an identical declaration sends it and marks the entry verified.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from src.infrastructure.mcp.catalogue_snapshot import build_snapshot, catalogue_fingerprint
from src.infrastructure.mcp.pool_catalogue import normalize_tool
from src.infrastructure.mcp.rate_limit import MCPDeclarationChangedError
from src.infrastructure.mcp.user_pool import PoolEntry, UserMCPClientPool
from src.infrastructure.observability.metrics_mcp import mcp_user_declaration_checks_total

pytestmark = pytest.mark.unit

SEARCH = {
    "name": "search",
    "description": "Search the notes",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
        "required": ["query"],
    },
    "output_schema": None,
    "title": None,
    "annotations": None,
    "app_resource_uri": None,
    "app_visibility": None,
}


def _declared(**changes: Any) -> SimpleNamespace:
    """The tool as the server lists it NOW (SDK shape)."""
    spec = {**SEARCH, **changes}
    return SimpleNamespace(
        name=spec["name"],
        description=spec["description"],
        input_schema=spec["input_schema"],
        output_schema=None,
        annotations=spec.get("annotations"),
        title=None,
        meta=None,
    )


class Server:
    """One MCP session: what ``tools/list`` answers now, and every call it received."""

    def __init__(self, *tools: SimpleNamespace) -> None:
        self.tools = list(tools)
        self.listings = 0
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def list_tools(self, **_: Any) -> Any:
        self.listings += 1
        return SimpleNamespace(tools=self.tools, next_cursor=None)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((name, arguments))
        return SimpleNamespace(is_error=False, content=[SimpleNamespace(text="found")])


class Bench:
    def __init__(
        self, server: Server, *, verified: bool, tools: list[dict[str, Any]] | None = None
    ) -> None:
        self.server = server
        self.user_id, self.server_id = uuid4(), uuid4()
        self.stale: list[tuple[UUID, UUID]] = []
        self.pool = UserMCPClientPool()
        self.pool._raise_if_cooling = AsyncMock()  # type: ignore[method-assign]
        self.pool._check_rate_limit = AsyncMock()  # type: ignore[method-assign]
        self.pool.on_stale_catalogue = lambda user_id, server_id: self.stale.append(
            (user_id, server_id)
        )
        self.entry = self.pool.hydrate(
            user_id=self.user_id,
            server_id=self.server_id,
            url="https://notes.example/mcp",
            auth=None,
            timeout_seconds=30,
            extra_headers=None,
            snapshot=build_snapshot(
                tools=tools or [SEARCH],
                configuration_fingerprint="cfg",
                discovered_at=datetime.now(UTC),
                generation=1,
            ),
            verified=verified,
        )

    async def call(self, arguments: dict[str, Any], tool: str = "search", **built: Any) -> str:
        @asynccontextmanager
        async def ephemeral(*_: Any, **__: Any) -> AsyncIterator[Server]:
            yield self.server

        with patch("src.infrastructure.mcp.user_pool._ephemeral_client", ephemeral):
            return await self.pool.call_tool(self.user_id, self.server_id, tool, arguments, **built)


def _count(outcome: str) -> float:
    return float(mcp_user_declaration_checks_total.labels(outcome=outcome)._value.get())


async def test_verified_entry_calls_without_listing() -> None:
    bench = Bench(Server(_declared()), verified=True)

    assert await bench.call({"query": "tax"}) == "found"

    assert bench.server.listings == 0 and bench.server.calls == [("search", {"query": "tax"})]


async def test_unverified_identical_calls_and_marks_verified() -> None:
    bench = Bench(Server(_declared()), verified=False)
    before = _count("identical")

    assert await bench.call({"query": "tax"}) == "found"

    assert bench.server.listings == 1 and len(bench.server.calls) == 1
    assert bench.entry.catalogue_verified is True and bench.stale == []
    assert _count("identical") == before + 1

    await bench.call({"query": "rent"})  # verified now: no second listing
    assert bench.server.listings == 1


@pytest.mark.parametrize(
    "current",
    [
        _declared(description="Search every note, archived ones included"),
        _declared(
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                    "folder": {"type": "string"},
                },
                "required": ["query"],
            }
        ),
    ],
    ids=["new description", "added optional parameter"],
)
async def test_compatible_change_calls_and_schedules_revalidation(current: SimpleNamespace) -> None:
    bench = Bench(Server(current), verified=False)
    before = _count("compatible")

    assert await bench.call({"query": "tax", "limit": 3}) == "found"

    assert len(bench.server.calls) == 1
    assert bench.stale == [(bench.user_id, bench.server_id)]
    assert bench.entry.catalogue_verified is False
    assert _count("compatible") == before + 1


@pytest.mark.parametrize(
    ("current", "arguments"),
    [
        (
            _declared(
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}, "scope": {"type": "string"}},
                    "required": ["query", "scope"],
                }
            ),
            {"query": "tax"},
        ),
        (
            _declared(
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                }
            ),
            {"query": "tax", "limit": 3},
        ),
        (
            _declared(
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "integer"}},
                    "required": ["query"],
                }
            ),
            {"query": "tax"},
        ),
    ],
    ids=["new required parameter", "removed parameter", "changed type"],
)
async def test_incompatible_change_refuses_without_calling(
    current: SimpleNamespace, arguments: dict[str, Any]
) -> None:
    bench = Bench(Server(current), verified=False)
    before = _count("incompatible")

    with pytest.raises(MCPDeclarationChangedError) as refused:
        await bench.call(arguments)

    assert refused.value.reason == "incompatible"
    assert bench.server.calls == []
    assert bench.stale == [(bench.user_id, bench.server_id)]
    assert _count("incompatible") == before + 1


async def test_newly_destructive_annotation_refuses() -> None:
    bench = Bench(
        Server(_declared(annotations={"readOnlyHint": False, "destructiveHint": True})),
        verified=False,
    )

    with pytest.raises(MCPDeclarationChangedError) as refused:
        await bench.call({"query": "tax"})

    assert refused.value.reason == "tightened" and bench.server.calls == []


async def test_a_loosened_annotation_is_only_compatible() -> None:
    """Only a TIGHTER declaration refuses; a server claiming read-only is not believed."""
    bench = Bench(Server(_declared(annotations={"readOnlyHint": True})), verified=False)

    assert await bench.call({"query": "tax"}) == "found"
    assert bench.stale == [(bench.user_id, bench.server_id)]


async def test_missing_tool_refuses() -> None:
    bench = Bench(Server(_declared(name="lookup")), verified=False)

    with pytest.raises(MCPDeclarationChangedError) as refused:
        await bench.call({"query": "tax"})

    assert refused.value.reason == "missing" and bench.server.calls == []


async def test_adapter_maps_a_changed_declaration_to_conflict() -> None:
    from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter

    adapter = UserMCPToolAdapter.from_discovered_tool(
        server_id=uuid4(),
        user_id=uuid4(),
        server_name="Notes",
        tool_name="search",
        description="Search",
        input_schema={},
    )
    pool = AsyncMock()
    pool.call_tool.side_effect = MCPDeclarationChangedError("incompatible")
    with (
        patch("src.infrastructure.mcp.user_pool.get_user_mcp_pool", return_value=pool),
        patch("src.infrastructure.mcp.user_tool_adapter.mcp_connection_errors_total") as errors,
    ):
        result = await adapter._arun()

    assert not result.success
    assert result.error_code == "CONFLICT"
    assert result.metadata["reason"] == "incompatible"
    errors.labels.assert_not_called()  # the server answered: not a connection failure


async def test_react_confirmation_identical_after_hydration() -> None:
    """M6: the confirmation a hydrated tool owes is the one its discovery gave."""
    from src.core.context import UserMCPToolsContext
    from src.infrastructure.mcp.pool_catalogue import PoolEntry as Entry
    from src.infrastructure.mcp.user_context import _register_user_standard_server

    destructive = {**SEARCH, "name": "purge", "annotations": {"destructive_hint": True}}
    server = SimpleNamespace(
        id=uuid4(),
        name="Notes",
        url="https://notes.example/mcp",
        timeout_seconds=30,
        domain_description=None,
        discovered_tools_cache=None,
    )
    discovered = Entry(user_id=uuid4(), server_id=server.id, last_used=0.0, tools=[destructive])
    hydrated = UserMCPClientPool().hydrate(
        user_id=discovered.user_id,
        server_id=server.id,
        url=server.url,
        auth=None,
        timeout_seconds=30,
        extra_headers=None,
        snapshot=build_snapshot(
            tools=[destructive],
            configuration_fingerprint="cfg",
            discovered_at=datetime.now(UTC),
            generation=1,
        ),
        verified=True,
    )

    def confirmation(entry: PoolEntry) -> list[tuple[Any, ...]]:
        ctx = UserMCPToolsContext()
        _register_user_standard_server(
            server, entry, discovered.user_id, ctx, False, {}, "mcp_notes", "abcd1234"  # type: ignore[arg-type]
        )
        return [
            (m.name, m.mutation_policy, m.permissions.hitl_required, m.tool_category)
            for m in ctx.tool_manifests
        ]

    assert confirmation(hydrated) == confirmation(discovered)
    assert confirmation(hydrated)[0][1] == "confirm"


async def test_the_stale_handler_is_installed_at_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pool cannot import the revalidation (the revalidation imports the pool):
    the composition root hands the scheduler to the pool it creates."""
    from src.core.config import settings
    from src.infrastructure.mcp.catalogue_revalidation import schedule_catalogue_revalidation
    from src.infrastructure.startup.integrations import init_user_mcp_pool

    pool = UserMCPClientPool()
    monkeypatch.setattr(
        "src.infrastructure.mcp.user_pool.initialize_user_mcp_pool", AsyncMock(return_value=pool)
    )
    monkeypatch.setattr(settings, "mcp_user_enabled", True)
    try:
        await init_user_mcp_pool()
        assert pool.on_stale_catalogue is schedule_catalogue_revalidation
    finally:
        monkeypatch.setattr(settings, "mcp_user_enabled", False)
        await init_user_mcp_pool()  # the gateways back to their unconfigured state


def test_a_call_that_checked_nothing_settles_nothing() -> None:
    from src.infrastructure.mcp.declaration_check import settle_declaration

    entry = PoolEntry(
        user_id=uuid4(), server_id=uuid4(), last_used=0.0, tools=[SEARCH], catalogue_verified=False
    )
    stale: list[tuple[UUID, UUID]] = []
    counts = {outcome: _count(outcome) for outcome in ("identical", "compatible", "missing")}

    settle_declaration(
        entry, None, None, lambda user_id, server_id: stale.append((user_id, server_id))
    )

    assert stale == []
    assert entry.catalogue_verified is False  # an unchecked call verifies nothing
    assert {outcome: _count(outcome) for outcome in counts} == counts


# ---------------------------------------------------------------------------
# Fresh review I2 (2026-10-29): a verification is the WHOLE catalogue's, and a call is
# checked against the declaration it was built from, whichever entry the pool now holds.
# ---------------------------------------------------------------------------

PURGE = {**SEARCH, "name": "purge", "description": "Archive a note"}


def _listed(spec: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        name=spec["name"],
        description=spec["description"],
        input_schema=spec["input_schema"],
        output_schema=None,
        annotations=spec.get("annotations"),
        title=None,
        meta=None,
    )


async def test_one_unchanged_tool_does_not_verify_a_catalogue_that_changed_elsewhere() -> None:
    """Reproduced by the review: calling an unchanged tool marked the whole server
    verified, and a tool that had become destructive was then called unchecked."""
    destructive = {**PURGE, "annotations": {"readOnlyHint": False, "destructiveHint": True}}
    bench = Bench(
        Server(_listed(SEARCH), _listed(destructive)), verified=False, tools=[SEARCH, PURGE]
    )

    assert await bench.call({"query": "tax"}) == "found"

    assert bench.entry.catalogue_verified is False
    assert bench.stale == [(bench.user_id, bench.server_id)]
    with pytest.raises(MCPDeclarationChangedError) as refused:
        await bench.call({"query": "old"}, tool="purge")
    assert refused.value.reason == "tightened"
    assert bench.server.calls == [("search", {"query": "tax"})]


async def test_an_unchanged_catalogue_is_verified_whichever_tool_was_called() -> None:
    bench = Bench(Server(_listed(SEARCH), _listed(PURGE)), verified=False, tools=[SEARCH, PURGE])

    assert await bench.call({"query": "tax"}) == "found"

    assert bench.entry.catalogue_verified is True and bench.stale == []


async def test_a_call_built_from_an_older_catalogue_is_checked_on_a_fresh_entry() -> None:
    """Reproduced by the review: the turn's own aged catalogue scheduled the
    revalidation, which replaced the entry with a fresh, verified one; the turn's later
    calls, built from the old declaration, then went out unchecked."""
    destructive = {**SEARCH, "annotations": {"readOnlyHint": False, "destructiveHint": True}}
    # The entry holds what a discovery keeps: the normalized declaration.
    current = normalize_tool(_listed(destructive))
    bench = Bench(Server(_listed(destructive)), verified=True, tools=[current])

    with pytest.raises(MCPDeclarationChangedError) as refused:
        await bench.call(
            {"query": "tax"},
            built_from=catalogue_fingerprint([SEARCH]),
            declaration=SEARCH,
        )

    assert refused.value.reason == "tightened"
    assert bench.server.listings == 1 and bench.server.calls == []
    assert bench.stale == []  # the entry itself is current: nothing to revalidate


async def test_a_call_built_from_the_current_catalogue_of_a_verified_entry_lists_nothing() -> None:
    bench = Bench(Server(_listed(SEARCH)), verified=True)

    await bench.call(
        {"query": "tax"}, built_from=bench.entry.catalogue_fingerprint, declaration=SEARCH
    )

    assert bench.server.listings == 0


async def test_the_adapter_hands_the_pool_what_its_call_was_built_from() -> None:
    from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter

    adapter = UserMCPToolAdapter.from_discovered_tool(
        server_id=uuid4(),
        user_id=uuid4(),
        server_name="Notes",
        tool_name="search",
        description="Search",
        input_schema=SEARCH["input_schema"],
        built_from="fp-1",
        declaration=SEARCH,
    )
    pool = AsyncMock()
    pool.call_tool.return_value = "found"
    with patch("src.infrastructure.mcp.user_pool.get_user_mcp_pool", return_value=pool):
        await adapter._arun(query="tax")

    assert pool.call_tool.await_args.kwargs["built_from"] == "fp-1"
    assert pool.call_tool.await_args.kwargs["declaration"] == SEARCH


async def test_a_registered_server_builds_its_adapters_from_the_entry_they_came_from() -> None:
    from src.core.context import UserMCPToolsContext
    from src.infrastructure.mcp.user_context import _register_user_standard_server

    server = SimpleNamespace(
        id=uuid4(),
        name="Notes",
        url="https://notes.example/mcp",
        timeout_seconds=30,
        domain_description=None,
        discovered_tools_cache=None,
    )
    entry = UserMCPClientPool().hydrate(
        user_id=uuid4(),
        server_id=server.id,
        url=server.url,
        auth=None,
        timeout_seconds=30,
        extra_headers=None,
        snapshot=build_snapshot(
            tools=[SEARCH],
            configuration_fingerprint="cfg",
            discovered_at=datetime.now(UTC),
            generation=1,
        ),
        verified=True,
    )
    ctx = UserMCPToolsContext()
    _register_user_standard_server(
        server, entry, entry.user_id, ctx, False, {}, "mcp_notes", "abcd1234"  # type: ignore[arg-type]
    )

    (adapter,) = ctx.tool_instances.values()
    assert adapter._built_from == entry.catalogue_fingerprint
    assert adapter._declaration == SEARCH
