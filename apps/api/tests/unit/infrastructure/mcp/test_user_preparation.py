"""A turn prepares its personal servers in parallel, from memory or the persisted catalogue first.

Spec 2026-10-21 §5.2-5.3 (M2). The servers used to be prepared one after the
other, each discovered over the network whenever the worker held nothing for
it. The real pool runs here; only the network (``_discover_tools``), the
failure pause, the publication, the vectors and the scheduling are doubles.
Concurrency is proven with events, never with a duration alone.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Coroutine, Iterator
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from src.core.config import settings
from src.core.context import UserMCPToolsContext, user_mcp_tools_ctx
from src.core.time_utils import now_utc
from src.infrastructure.mcp.auth import MCPOAuth2Auth
from src.infrastructure.mcp.catalogue_fingerprint import connection_fingerprint
from src.infrastructure.mcp.catalogue_snapshot import (
    CatalogueSnapshot,
    build_snapshot,
    snapshot_to_jsonb,
)
from src.infrastructure.mcp.rate_limit import MCPServerPausedError
from src.infrastructure.mcp.user_pool import DiscoveredCatalogue, UserMCPClientPool
from src.infrastructure.mcp.user_preparation import (
    PreparationEvent,
    ServerPreparation,
    prepare_user_servers,
)

pytestmark = pytest.mark.unit

MODULE = "src.infrastructure.mcp.user_preparation"


def _tool(name: str) -> dict[str, Any]:
    return {"name": name, "description": f"{name} records", "input_schema": {"type": "object"}}


class Failures:
    """The pool's failure pause, in memory."""

    def __init__(self) -> None:
        self.paused: dict[tuple[UUID, UUID], float] = {}
        self.recorded: list[tuple[UUID, UUID]] = []

    async def remaining(self, key: tuple[UUID, UUID]) -> float:
        return self.paused.get(key, 0.0)

    async def record(self, key: tuple[UUID, UUID]) -> float:
        self.recorded.append(key)
        return 30.0

    async def clear(self, key: tuple[UUID, UUID]) -> None:
        self.paused.pop(key, None)


class Fleet:
    """Personal servers, a real pool over a scripted network, what the turns published."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.user_id = uuid4()
        self.failures = Failures()
        self.pool = self.new_pool()
        self.network: dict[str, list[dict[str, Any]] | BaseException] = {}
        self.gates: dict[str, asyncio.Event] = {}
        self.entered: list[str] = []
        self.timeouts: dict[str, int] = {}
        self.inside = 0
        self.max_inside = 0
        self.contexts_seen: list[object] = []
        self.events: list[PreparationEvent] = []
        self.published: list[CatalogueSnapshot] = []
        self.scheduled: list[tuple[UUID, UUID]] = []
        self.children: list[asyncio.Task[Any]] = []
        self.servers: list[SimpleNamespace] = []
        monkeypatch.setattr(f"{MODULE}.publish_catalogue_if_current", self.publish)
        monkeypatch.setattr(
            f"{MODULE}.schedule_catalogue_revalidation",
            lambda user_id, server_id: self.scheduled.append((user_id, server_id)),
        )
        monkeypatch.setattr(f"{MODULE}.usable_tool_embeddings", AsyncMock(return_value={}))
        monkeypatch.setattr(f"{MODULE}.safe_fire_and_forget", self.own)

    def new_pool(self) -> UserMCPClientPool:
        """Another worker's pool: empty, same network, same pause."""
        pool = UserMCPClientPool(failures=self.failures)  # type: ignore[arg-type]
        pool._raise_if_cooling = AsyncMock()  # type: ignore[method-assign]
        pool._discover_tools = self.discover  # type: ignore[method-assign]
        return pool

    def own(self, coro: Coroutine[Any, Any, Any], **_: Any) -> asyncio.Task[Any]:
        task = asyncio.get_running_loop().create_task(coro)
        self.children.append(task)
        return task

    async def discover(
        self,
        url: str,
        auth: object,
        timeout_seconds: int,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> DiscoveredCatalogue:
        self.entered.append(url)
        self.timeouts[url] = timeout_seconds
        self.contexts_seen.append(user_mcp_tools_ctx.get())
        self.inside += 1
        self.max_inside = max(self.max_inside, self.inside)
        try:
            gate = self.gates.get(url)
            if gate is not None:
                await gate.wait()
            answer = self.network[url]
            if isinstance(answer, BaseException):
                raise answer
            return DiscoveredCatalogue(tools=sorted(answer, key=lambda tool: tool["name"]))
        finally:
            self.inside -= 1

    async def publish(
        self, *, user_id: UUID, server_id: UUID, snapshot: CatalogueSnapshot, tool_embeddings: Any
    ) -> str:
        self.published.append(snapshot)
        for server in self.servers:
            if server.id == server_id:
                server.discovered_tools_cache = snapshot_to_jsonb(snapshot)
        return "published"

    def server(
        self,
        name: str,
        tools: list[dict[str, Any]] | BaseException,
        *,
        timeout: int = 30,
        snapshot_age: float | None = None,
        generation: int = 1,
    ) -> SimpleNamespace:
        server = SimpleNamespace(
            id=uuid4(),
            user_id=self.user_id,
            name=name,
            url=f"https://{name.lower()}.example/mcp",
            timeout_seconds=timeout,
            extra_headers=None,
            discovered_tools_cache=None,
            hitl_required=False,
            iterative_mode=False,
            domain_description=None,
            auth_type="none",
        )
        self.network[server.url] = tools
        if snapshot_age is not None and isinstance(tools, list):
            server.discovered_tools_cache = self.snapshot_of(
                server, tools, snapshot_age, generation
            )
        self.servers.append(server)
        return server

    @staticmethod
    def snapshot_of(
        server: SimpleNamespace, tools: list[dict[str, Any]], age: float, generation: int
    ) -> dict[str, Any]:
        return snapshot_to_jsonb(
            build_snapshot(
                tools=tools,
                configuration_fingerprint=connection_fingerprint(
                    server.url, None, server.timeout_seconds, None
                ),
                discovered_at=now_utc() - timedelta(seconds=age),
                generation=generation,
            )
        )

    async def prepare(
        self,
        servers: list[SimpleNamespace],
        *,
        ceiling: float = 30.0,
        pool: UserMCPClientPool | None = None,
    ) -> list[ServerPreparation]:
        return await prepare_user_servers(
            self.user_id,
            servers,  # type: ignore[arg-type]
            pool or self.pool,
            on_event=self.events.append,
            ceiling_s=ceiling,
            auth_for=lambda server: None,  # type: ignore[arg-type,return-value]
        )

    async def until_entered(self, count: int) -> None:
        async def wait() -> None:
            while len(self.entered) < count:
                await asyncio.sleep(0)

        await asyncio.wait_for(wait(), timeout=5)

    def phases(self, server: SimpleNamespace) -> list[str]:
        return [event.phase for event in self.events if event.server_id == server.id]


@pytest.fixture
def fleet(monkeypatch: pytest.MonkeyPatch) -> Iterator[Fleet]:
    fleet = Fleet(monkeypatch)
    yield fleet
    for task in fleet.children:
        task.cancel()


def _fresh() -> float:
    return 1.0


def _aged() -> float:
    return settings.mcp_user_catalogue_revalidate_after_seconds + 60.0


# --- parallelism -------------------------------------------------------------


async def test_servers_prepared_concurrently(fleet: Fleet) -> None:
    alpha, beta = fleet.server("Alpha", [_tool("a")]), fleet.server("Beta", [_tool("b")])
    fleet.gates = {alpha.url: asyncio.Event(), beta.url: asyncio.Event()}
    turn = asyncio.create_task(fleet.prepare([alpha, beta]))

    await fleet.until_entered(2)
    assert set(fleet.entered) == {alpha.url, beta.url}  # both on the network, neither answered
    for gate in fleet.gates.values():
        gate.set()

    assert [result.outcome for result in await turn] == ["ready", "ready"]


async def test_semaphore_bounds_network_preparations(fleet: Fleet) -> None:
    slots = settings.mcp_user_preparation_concurrency
    servers = [fleet.server(f"S{i}", [_tool(f"t{i}")]) for i in range(slots + 1)]
    fleet.gates = {server.url: asyncio.Event() for server in servers}
    turn = asyncio.create_task(fleet.prepare(servers))

    await fleet.until_entered(slots)
    for _ in range(50):
        await asyncio.sleep(0)
    assert len(fleet.entered) == slots  # the last one waits for a slot
    for gate in fleet.gates.values():
        gate.set()

    assert all(result.outcome == "ready" for result in await turn)
    assert fleet.max_inside == slots and len(fleet.entered) == slots + 1


async def test_one_failure_keeps_other_servers(fleet: Fleet) -> None:
    up = fleet.server("Up", [_tool("search")])
    down = fleet.server("Down", RuntimeError("unreachable"))

    ok, failed = await fleet.prepare([up, down])

    assert ok.outcome == "ready" and ok.entry is not None
    assert [tool["name"] for tool in ok.entry.tools] == ["search"]
    assert failed.outcome == "failed" and isinstance(failed.error, RuntimeError)
    assert fleet.phases(down)[-1] == "failed"


async def test_failures_isolated_not_gathered(fleet: Fleet) -> None:
    slow = fleet.server("Slow", [_tool("search")])
    broken = fleet.server("Broken", RuntimeError("boom"))
    fleet.gates[slow.url] = asyncio.Event()
    turn = asyncio.create_task(fleet.prepare([slow, broken]))

    async def broken_settled() -> None:
        while "failed" not in fleet.phases(broken):
            await asyncio.sleep(0)

    await asyncio.wait_for(broken_settled(), timeout=5)
    assert not turn.done()  # the failure cancelled nothing: Slow is still discovering
    fleet.gates[slow.url].set()

    assert [result.outcome for result in await turn] == ["ready", "failed"]


async def test_a_failing_event_sink_costs_no_server(fleet: Fleet) -> None:
    """Progress is a side channel: a reader that raises never fails a server."""
    cold = fleet.server("Cold", [_tool("a")])
    warm = fleet.server("Warm", [_tool("b")], snapshot_age=_fresh())

    def broken(event: PreparationEvent) -> None:
        raise RuntimeError("sink down")

    results = await prepare_user_servers(
        fleet.user_id,
        [cold, warm],  # type: ignore[list-item]
        fleet.pool,
        on_event=broken,
        ceiling_s=5,
        auth_for=lambda server: None,  # type: ignore[arg-type,return-value]
    )

    assert [result.outcome for result in results] == ["ready", "ready"]


async def test_every_preparation_source_is_counted(fleet: Fleet) -> None:
    """The reuse panel keeps seeing the turns that went to the network."""
    from src.infrastructure.observability.metrics_mcp import mcp_catalogue_cache_total

    def count(result: str) -> float:
        return float(mcp_catalogue_cache_total.labels(result=result)._value.get())

    before = {result: count(result) for result in ("miss", "hit", "snapshot")}
    server = fleet.server("Notes", [_tool("search")])
    await fleet.prepare([server])  # the network
    await fleet.prepare([server])  # this worker's entry
    await fleet.prepare([server], pool=fleet.new_pool())  # another worker: the snapshot

    assert {result: count(result) - before[result] for result in before} == {
        "miss": 1,
        "hit": 1,
        "snapshot": 1,
    }


async def test_child_never_sets_contextvar(fleet: Fleet) -> None:
    assert user_mcp_tools_ctx.get() is None
    await fleet.prepare([fleet.server("Alpha", [_tool("a")])])

    assert fleet.contexts_seen == [None]
    assert user_mcp_tools_ctx.get() is None


# --- the persisted catalogue -------------------------------------------------


async def test_warm_catalogue_needs_no_network(fleet: Fleet) -> None:
    from src.infrastructure.mcp.user_context import _register_user_standard_server

    server = fleet.server("Notes", [_tool("search"), _tool("fetch"), _tool("append")])
    (cold,) = await fleet.prepare([server])
    assert len(fleet.entered) == 1 and len(fleet.published) == 1

    (warm,) = await fleet.prepare([server], pool=fleet.new_pool())  # another worker

    assert len(fleet.entered) == 1  # no network
    assert warm.source == "catalogue" and warm.entry is not None and cold.entry is not None
    assert warm.entry.from_snapshot is True

    def registered(entry: Any) -> UserMCPToolsContext:
        ctx = UserMCPToolsContext()
        _register_user_standard_server(
            server, entry, fleet.user_id, ctx, False, {}, "mcp_notes", "abcd1234"  # type: ignore[arg-type]
        )
        return ctx

    discovered, hydrated = registered(cold.entry), registered(warm.entry)
    assert [m.name for m in hydrated.tool_manifests] == [m.name for m in discovered.tool_manifests]
    assert hydrated.server_catalogue_fingerprints == discovered.server_catalogue_fingerprints
    assert hydrated.server_description_sources == {"Notes": "snapshot"}


async def test_aged_snapshot_served_and_revalidation_scheduled(fleet: Fleet) -> None:
    server = fleet.server("Notes", [_tool("search")], snapshot_age=_aged())

    (result,) = await fleet.prepare([server])

    assert result.outcome == "ready" and result.source == "catalogue"
    assert result.entry is not None and result.entry.catalogue_verified is False
    assert fleet.entered == []
    assert fleet.scheduled == [(fleet.user_id, server.id)]


async def test_a_warm_entry_that_aged_is_served_and_revalidated(fleet: Fleet) -> None:
    server = fleet.server("Notes", [_tool("search")])
    await fleet.prepare([server])
    entry = fleet.pool._entries[(fleet.user_id, server.id)]
    entry.discovered_at -= _aged()  # the worker kept it past its revalidation age

    (result,) = await fleet.prepare([server])

    assert result.entry is entry and entry.catalogue_verified is False
    assert len(fleet.entered) == 1  # served, not rediscovered on the turn
    assert fleet.scheduled == [(fleet.user_id, server.id)]


async def test_a_zero_ttl_is_no_hint_never_a_listing_before_every_call(fleet: Fleet) -> None:
    """The official SDK declares ``ttlMs: 0`` by default (measured): it is the absence of
    a hint, not a server asking to be checked on every turn. Read as « verify at use »,
    it put a full listing before the first call of every turn of every such server;
    the setting's horizon decides both the verification and the revalidation."""
    server = fleet.server("Notes", [_tool("search")], snapshot_age=5.0)
    stored = dict(server.discovered_tools_cache)
    stored["server_ttl_ms"] = 0
    server.discovered_tools_cache = stored

    (recent,) = await fleet.prepare([server])
    assert recent.entry is not None and recent.entry.catalogue_verified is True
    assert fleet.scheduled == []

    (again,) = await fleet.prepare([server])  # the next turn, on the warm entry
    assert again.entry is recent.entry and again.entry.catalogue_verified is True

    recent.entry.discovered_at -= _aged()
    (aged,) = await fleet.prepare([server])
    assert aged.entry is not None and aged.entry.catalogue_verified is False
    assert fleet.scheduled == [(fleet.user_id, server.id)]
    assert fleet.entered == []


async def test_fresh_snapshot_needs_no_revalidation(fleet: Fleet) -> None:
    server = fleet.server("Notes", [_tool("search")], snapshot_age=_fresh())

    (result,) = await fleet.prepare([server])

    assert result.entry is not None and result.entry.catalogue_verified is True
    assert fleet.entered == [] and fleet.scheduled == []


async def test_paused_server_not_offered(fleet: Fleet) -> None:
    server = fleet.server("Down", [_tool("search")], snapshot_age=_fresh())
    fleet.failures.paused[(fleet.user_id, server.id)] = 42.0

    (result,) = await fleet.prepare([server])

    assert result.outcome == "paused" and result.entry is None
    assert isinstance(result.error, MCPServerPausedError)
    assert fleet.entered == []


async def test_a_snapshot_of_another_configuration_is_a_miss(fleet: Fleet) -> None:
    server = fleet.server("Notes", [_tool("old")], snapshot_age=_fresh())
    server.url = "https://moved.example/mcp"  # edited after the snapshot was taken
    fleet.network[server.url] = [_tool("new")]

    (result,) = await fleet.prepare([server])

    assert result.source == "network" and fleet.entered == [server.url]
    assert result.entry is not None and [t["name"] for t in result.entry.tools] == ["new"]


async def test_newer_row_snapshot_replaces_the_warm_entry(fleet: Fleet) -> None:
    server = fleet.server("Notes", [_tool("v1")])
    await fleet.prepare([server])
    newer = fleet.published[0].generation + 1
    server.discovered_tools_cache = fleet.snapshot_of(server, [_tool("v2")], 1.0, newer)

    (result,) = await fleet.prepare([server])

    assert len(fleet.entered) == 1  # still no second discovery
    assert result.entry is not None and [t["name"] for t in result.entry.tools] == ["v2"]


async def test_snapshot_parsed_once_per_fingerprint(
    fleet: Fleet, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.infrastructure.mcp import user_pool

    calls: list[object] = []
    real = user_pool.parse_catalogue_snapshot

    def counted(raw: object) -> Any:
        calls.append(raw)
        return real(raw)

    monkeypatch.setattr(user_pool, "parse_catalogue_snapshot", counted)
    big = [_tool(f"tool_{i:03d}") for i in range(settings.mcp_max_tools_per_server)]
    server = fleet.server("Big", big, snapshot_age=_fresh(), generation=5)

    for _ in range(3):
        await fleet.prepare([server])
    assert len(calls) == 1

    server.discovered_tools_cache = fleet.snapshot_of(server, big[:-1], 1.0, 6)
    await fleet.prepare([server])
    assert len(calls) == 2 and fleet.entered == []


async def test_evicted_entry_rehydrated(fleet: Fleet) -> None:
    server = fleet.server("Notes", [_tool("search")])
    await fleet.prepare([server])
    await fleet.pool.disconnect(fleet.user_id, server.id)  # idle eviction

    (result,) = await fleet.prepare([server])

    assert len(fleet.entered) == 1
    assert result.outcome == "ready" and result.entry is not None
    assert result.entry.from_snapshot is True


async def test_hydrated_oauth_server_refreshes_on_first_call(fleet: Fleet) -> None:
    """The hydrated entry keeps the row's auth: the first call runs its refresh flow."""
    server = fleet.server("Calendar", [_tool("events")], snapshot_age=_fresh())
    auth = SimpleNamespace(catalogue_identity="grant-1")
    server.discovered_tools_cache = snapshot_to_jsonb(
        build_snapshot(
            tools=[_tool("events")],
            configuration_fingerprint=connection_fingerprint(server.url, auth, 30, None),
            discovered_at=now_utc(),
            generation=1,
        )
    )
    (result,) = await prepare_user_servers(
        fleet.user_id,
        [server],  # type: ignore[list-item]
        fleet.pool,
        on_event=None,
        ceiling_s=5,
        auth_for=lambda row: auth,  # type: ignore[arg-type,return-value]
    )
    assert fleet.entered == [] and result.entry is not None
    seen: list[object] = []

    async def execute(**arguments: Any) -> str:
        seen.append(arguments["auth"])
        return "ok"

    fleet.pool._execute_call_ephemeral = execute  # type: ignore[method-assign]
    fleet.pool._check_rate_limit = AsyncMock()  # type: ignore[method-assign]
    await fleet.pool.call_tool(fleet.user_id, server.id, "events", {})

    assert seen == [auth]


class _ExpiredGrantServer:
    """An MCP endpoint refusing the stored token, and a token endpoint refusing its refresh."""

    def __init__(self) -> None:
        self.paths: list[str] = []
        recorder = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: object) -> None:
                return

            def _answer(self, status: int, body: dict[str, Any]) -> None:
                payload = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_POST(self) -> None:  # noqa: N802 - the http.server contract
                self.rfile.read(int(self.headers.get("content-length") or 0))
                recorder.paths.append(self.path)
                if self.path == "/token":
                    self._answer(400, {"error": "invalid_grant"})
                else:
                    self._answer(401, {"error": "invalid_token"})

            do_GET = do_POST  # noqa: N815 - the SDK may open its event stream

        self._http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._http.server_address[1]
        threading.Thread(target=self._http.serve_forever, daemon=True).start()

    def close(self) -> None:
        self._http.shutdown()
        self._http.server_close()


async def test_hydrated_oauth_server_whose_refresh_fails_is_auth_required_never_empty(
    fleet: Fleet, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review focus 2: a catalogue hydrated without network keeps the row's OAuth flow.

    The first call meets the expired token, runs the REAL refresh, is refused
    (``invalid_grant``): the server is marked ``auth_required`` and the call fails —
    never a silent success, and the hydrated catalogue is not emptied.
    """
    remote = _ExpiredGrantServer()
    marked: list[bool] = []

    async def stored() -> dict[str, Any]:
        return {"access_token": "expired", "refresh_token": "refresh", "client_id": "lia"}

    async def never_updated(_credentials: dict[str, Any]) -> None:
        raise AssertionError("a refused refresh persists nothing")

    async def mark_auth_required() -> None:
        marked.append(True)

    monkeypatch.setattr(
        "src.infrastructure.cache.redis.get_redis_session",
        AsyncMock(side_effect=ConnectionError("no cache: the refresh proceeds unlocked")),
    )
    try:
        server = fleet.server("Calendar", [_tool("events")])
        server.url = f"http://127.0.0.1:{remote.port}/mcp"
        auth = MCPOAuth2Auth(
            server_id=server.id,
            get_creds_fn=stored,
            update_creds_fn=never_updated,
            mark_auth_required_fn=mark_auth_required,
            token_endpoint=f"http://127.0.0.1:{remote.port}/token",
            client_id="lia",
        )
        server.discovered_tools_cache = snapshot_to_jsonb(
            build_snapshot(
                tools=[_tool("events")],
                configuration_fingerprint=connection_fingerprint(server.url, auth, 30, None),
                discovered_at=now_utc(),
                generation=1,
            )
        )
        (result,) = await prepare_user_servers(
            fleet.user_id,
            [server],  # type: ignore[list-item]
            fleet.pool,
            on_event=None,
            ceiling_s=5,
            auth_for=lambda row: auth,  # type: ignore[arg-type,return-value]
        )
        assert fleet.entered == [] and result.entry is not None  # hydrated, no network
        fleet.pool._check_rate_limit = AsyncMock()  # type: ignore[method-assign]

        with pytest.raises(Exception):  # noqa: B017 - the refusal, not its wrapper class
            await fleet.pool.call_tool(fleet.user_id, server.id, "events", {})

        # The refresh flow ran ONCE: the SDK's legacy fallback request meets the same
        # refused grant and never replays it; each refused request still says so.
        assert remote.paths.count("/token") == 1
        assert marked and all(marked)
        assert [tool["name"] for tool in result.entry.tools] == ["events"]  # never emptied
    finally:
        remote.close()


# --- the ceiling and the notices --------------------------------------------


async def test_ceiling_continues_without_cold_server(fleet: Fleet) -> None:
    warm = fleet.server("Warm", [_tool("search")], snapshot_age=_fresh())
    cold = fleet.server("Cold", [_tool("fetch")])
    fleet.gates[cold.url] = asyncio.Event()

    ready, deferred = await fleet.prepare([warm, cold], ceiling=0.05)

    assert (ready.outcome, deferred.outcome) == ("ready", "deferred")
    assert deferred.entry is None
    assert fleet.phases(cold)[-1] == "deferred" and "deferred" not in fleet.phases(warm)
    child = fleet.children[1]
    assert not child.done()  # Q2 (a): the discovery keeps running for the next turn
    fleet.gates[cold.url].set()
    finished = await child
    assert finished.outcome == "ready" and len(fleet.published) == 1

    (next_turn,) = await fleet.prepare([cold], pool=fleet.new_pool())
    assert next_turn.outcome == "ready" and next_turn.source == "catalogue"
    assert fleet.entered == [cold.url]


async def test_slow_notice_for_a_server_still_discovering(
    fleet: Fleet, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "mcp_user_slow_preparation_notice_seconds", 0.02)
    warm = fleet.server("Warm", [_tool("search")], snapshot_age=_fresh())
    cold = fleet.server("Cold", [_tool("fetch")])
    fleet.gates[cold.url] = asyncio.Event()
    turn = asyncio.create_task(fleet.prepare([warm, cold]))

    async def slow_seen() -> None:
        while "slow" not in fleet.phases(cold):
            await asyncio.sleep(0.005)

    await asyncio.wait_for(slow_seen(), timeout=5)
    fleet.gates[cold.url].set()
    await turn

    assert fleet.phases(cold) == ["queued", "discovering", "slow", "embeddings", "ready"]
    assert fleet.phases(warm) == ["queued", "embeddings", "ready"]


async def test_a_server_waiting_for_a_discovery_slot_is_told_slow_then_deferred(
    fleet: Fleet, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fresh review I4: « slow » went only to a server already on the network, and the
    deferral notice only to a « slow » one — a server waiting for a discovery slot (or a
    lock) was left out at the ceiling with no notice, its tools silently gone (Q2 (a))."""
    monkeypatch.setattr(settings, "mcp_user_slow_preparation_notice_seconds", 0.02)
    fleet.pool.discovery_slots = asyncio.Semaphore(1)
    first = fleet.server("First", [_tool("a")])
    queued = fleet.server("Queued", [_tool("b")])
    fleet.gates[first.url] = asyncio.Event()

    try:
        await fleet.prepare([first, queued], ceiling=0.08)
    finally:
        fleet.gates[first.url].set()

    assert fleet.phases(queued) == ["queued", "slow", "deferred"]
    assert fleet.phases(first) == ["queued", "discovering", "slow", "deferred"]


async def test_a_server_reaching_the_network_after_the_notice_delay_is_told_slow(
    fleet: Fleet, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It was still preparing when the notice delay passed, wherever it was waiting."""
    monkeypatch.setattr(settings, "mcp_user_slow_preparation_notice_seconds", 0.02)
    fleet.pool.discovery_slots = asyncio.Semaphore(1)
    first = fleet.server("First", [_tool("a")])
    later = fleet.server("Later", [_tool("b")])
    fleet.gates[first.url] = asyncio.Event()
    turn = asyncio.create_task(fleet.prepare([first, later]))

    async def told() -> None:
        while "slow" not in fleet.phases(later):
            await asyncio.sleep(0.005)

    await asyncio.wait_for(told(), timeout=5)
    fleet.gates[first.url].set()
    await turn

    assert fleet.phases(later)[:3] == ["queued", "slow", "discovering"]
    assert fleet.phases(later)[-1] == "ready"


async def test_discovery_timeout_is_dedicated(fleet: Fleet) -> None:
    patient = fleet.server("Patient", [_tool("a")], timeout=120)
    brief = fleet.server("Brief", [_tool("b")], timeout=1)

    await fleet.prepare([patient, brief])

    assert fleet.timeouts == {
        patient.url: min(settings.mcp_user_discovery_timeout_seconds, 120),
        brief.url: 1,
    }
    # The row's own timeout still governs the tool calls and the configuration.
    entry = fleet.pool._entries[(fleet.user_id, patient.id)]
    assert entry.timeout_seconds == 120


# --- the turn's assembly -----------------------------------------------------


def _wire_setup(
    fleet: Fleet, monkeypatch: pytest.MonkeyPatch, pools: list[UserMCPClientPool]
) -> None:
    """``setup_user_mcp_tools`` over the fleet: the last pool is the worker serving the turn."""
    from contextlib import asynccontextmanager

    class Repository:
        def __init__(self, db: object) -> None:
            pass

        async def get_enabled_active_for_user(self, user_id: UUID) -> list[SimpleNamespace]:
            return list(fleet.servers)

    @asynccontextmanager
    async def session() -> Any:
        yield object()

    monkeypatch.setattr(settings, "mcp_user_enabled", True)
    monkeypatch.setattr("src.infrastructure.mcp.user_context.get_user_mcp_pool", lambda: pools[-1])
    monkeypatch.setattr("src.infrastructure.mcp.user_context.build_auth_for_server", lambda r: None)
    monkeypatch.setattr("src.infrastructure.mcp.user_context.get_admin_mcp_domains", lambda: {})
    monkeypatch.setattr("src.infrastructure.mcp.registration.get_admin_mcp_domains", lambda: {})
    monkeypatch.setattr(
        "src.infrastructure.mcp.registration.get_admin_mcp_server_domains", lambda: {}
    )
    monkeypatch.setattr("src.domains.user_mcp.repository.UserMCPServerRepository", Repository)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)


async def _turn(fleet: Fleet) -> UserMCPToolsContext:
    from src.infrastructure.mcp.user_context import cleanup_user_mcp_tools, setup_user_mcp_tools

    token = await setup_user_mcp_tools(fleet.user_id)
    try:
        ctx = user_mcp_tools_ctx.get()
        assert token is not None and ctx is not None
        return ctx
    finally:
        cleanup_user_mcp_tools(token)


async def test_renamed_server_keeps_prefix_from_current_row(
    fleet: Fleet, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review focus 1: a rename changes no connection setting, so the snapshot still
    serves — and the domain, the agent and the prefix come from the CURRENT row."""
    server = fleet.server("Notes", [_tool("search")])
    pools = [fleet.pool]
    _wire_setup(fleet, monkeypatch, pools)

    first = await _turn(fleet)
    server.name = "Journal"
    pools.append(fleet.new_pool())  # another worker: only the persisted catalogue
    second = await _turn(fleet)

    assert len(fleet.entered) == 1
    assert first.server_domains == {"Notes": "mcp_notes"}
    assert second.server_domains == {"Journal": "mcp_journal"}
    assert {manifest.agent for manifest in second.tool_manifests} == {"mcp_journal_agent"}
    names = [manifest.name for manifest in second.tool_manifests]
    assert names == [manifest.name for manifest in first.tool_manifests]
    assert names == [f"mcp_user_{str(server.id)[:8]}_search"]


async def test_the_turn_assembles_in_the_servers_order_without_the_deferred_one(
    fleet: Fleet, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "mcp_user_preparation_ceiling_seconds", 0.05)
    fleet.server("Alpha", [_tool("a")], snapshot_age=_fresh())
    cold = fleet.server("Bravo", [_tool("b")])
    fleet.server("Charlie", [_tool("c")], snapshot_age=_fresh())
    fleet.gates[cold.url] = asyncio.Event()
    _wire_setup(fleet, monkeypatch, [fleet.pool])

    ctx = await _turn(fleet)

    assert list(ctx.server_domains) == ["Alpha", "Charlie"]
    assert user_mcp_tools_ctx.get() is None  # installed once, by the parent, then cleaned up
    fleet.gates[cold.url].set()
    await fleet.children[1]
    later = await _turn(fleet)
    assert list(later.server_domains) == ["Alpha", "Bravo", "Charlie"]


async def test_no_server_prepares_nothing(fleet: Fleet) -> None:
    assert await fleet.prepare([]) == []
    assert fleet.events == []


async def test_a_server_past_its_own_bound_is_timed_out_not_failed(fleet: Fleet) -> None:
    late = fleet.server("Late", TimeoutError("no answer"))

    (result,) = await fleet.prepare([late])

    assert result.outcome == "timed_out"
    assert isinstance(result.error, TimeoutError)
    assert fleet.phases(late)[-1] == "timed_out"


async def test_a_failed_publication_keeps_the_turns_catalogue(
    fleet: Fleet, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the next turns lose the shortcut: this turn already holds the tools."""
    cold = fleet.server("Cold", [_tool("search")])
    monkeypatch.setattr(
        f"{MODULE}.publish_catalogue_if_current",
        AsyncMock(side_effect=ConnectionError("database down")),
    )

    (result,) = await fleet.prepare([cold])

    assert result.outcome == "ready" and result.source == "network"
    assert result.entry is not None
    assert [tool["name"] for tool in result.entry.tools] == ["search"]


async def test_a_server_told_slow_then_paused_is_told_it_was_not_prepared(
    fleet: Fleet, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Third fresh review: « slow » now reaches a server waiting anywhere; one that then
    ended paused emitted nothing, so its notice stayed until the run ended and its tools
    vanished unexplained (Q2 (a) wants a notice)."""
    monkeypatch.setattr(settings, "mcp_user_slow_preparation_notice_seconds", 0.02)
    server = fleet.server("Down", [_tool("search")], snapshot_age=_fresh())

    async def slow_pause_answer(_key: object) -> float:
        await asyncio.sleep(0.06)
        return 42.0

    fleet.failures.remaining = slow_pause_answer  # type: ignore[method-assign]

    (result,) = await fleet.prepare([server])

    assert result.outcome == "paused"
    assert fleet.phases(server) == ["queued", "slow", "failed"]
