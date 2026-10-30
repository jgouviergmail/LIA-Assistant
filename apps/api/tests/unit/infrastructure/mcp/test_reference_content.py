"""A personal server's ``read_me`` is fetched at real use, never at discovery (M1b, spec §5.5b).

Discovery used to call ``read_me`` for every server exposing it, and the
registration then DROPPED the tool, so the ReAct loop could neither read the
reference nor call it (E10), while the planner matched raw server names against
domain slugs and missed « My Notion » (E9). The reference is now fetched when the
pipeline planner prepares a turn whose router-selected domains include the
server — once, bounded, under a claim shared by the workers —, kept on the
worker and in the snapshot, served while it is refreshed in the background once
old, and ReAct is offered ``read_me`` as an ordinary ReAct-only tool.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Coroutine, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from src.core.config import settings
from src.core.constants import EXECUTION_MODE_PIPELINE, EXECUTION_MODE_REACT
from src.core.context import UserMCPToolsContext
from src.domains.agents.registry.catalogue import manifests_for_mode
from src.infrastructure.mcp.catalogue_snapshot import (
    build_snapshot,
    catalogue_fingerprint,
    snapshot_to_jsonb,
)
from src.infrastructure.mcp.reference_content import (
    collect_user_references,
    reference_claim_key,
    reference_source,
)
from src.infrastructure.mcp.user_pool import PoolEntry, UserMCPClientPool
from src.infrastructure.observability.metrics_mcp import mcp_user_reference_fetches_total
from tests.helpers.mcp_reference_sources import USER_ID, reference_context
from tests.helpers.mcp_reference_sources import reference_source as stored_source
from tests.helpers.redis_double import InMemoryRedis

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 28, 9, 0, tzinfo=UTC)
MODULE = "src.infrastructure.mcp.reference_content"


class FakePool:
    """The pool's reference door: one answer (or failure) per call, every call recorded."""

    def __init__(self, *answers: str | None | BaseException) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[UUID, UUID, int]] = []

    async def fetch_reference(self, user_id: UUID, server_id: UUID, timeout_seconds: int) -> Any:
        self.calls.append((user_id, server_id, timeout_seconds))
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer


class Background:
    """A fire-and-forget double that OWNS what it receives: every coroutine is awaited."""

    def __init__(self) -> None:
        self.pending: list[Coroutine[Any, Any, Any]] = []

    def __call__(self, coro: Coroutine[Any, Any, Any], **_: Any) -> None:
        self.pending.append(coro)

    async def run(self) -> None:
        while self.pending:
            await self.pending.pop(0)


@contextmanager
def wired(
    pool: FakePool, *, redis: InMemoryRedis | None = None
) -> Iterator[tuple[Background, AsyncMock]]:
    background = Background()
    publish = AsyncMock(return_value="published")
    cache = redis or InMemoryRedis()
    with (
        patch(f"{MODULE}.get_user_mcp_pool", return_value=pool),
        patch(f"{MODULE}.get_redis_cache", new=AsyncMock(return_value=cache)),
        patch(f"{MODULE}.safe_fire_and_forget", new=background),
        patch(f"{MODULE}.publish_catalogue_if_current", new=publish),
    ):
        yield background, publish
    for coro in background.pending:
        coro.close()


def _count(outcome: str) -> float:
    return mcp_user_reference_fetches_total.labels(outcome=outcome)._value.get()


def _aged() -> datetime:
    return NOW - timedelta(seconds=settings.mcp_user_catalogue_revalidate_after_seconds + 1)


# --- discovery ---------------------------------------------------------------


async def test_discovery_never_calls_read_me() -> None:
    calls: list[str] = []

    class Client:
        instructions = None

        async def list_tools(self, **_: Any) -> Any:
            tools = [
                SimpleNamespace(
                    name=name,
                    description=name,
                    input_schema={"type": "object"},
                    output_schema=None,
                    annotations=None,
                    title=None,
                    meta=None,
                )
                for name in ("search", "read_me")
            ]
            return SimpleNamespace(tools=tools, next_cursor=None)

        async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
            calls.append(name)
            return SimpleNamespace(content=[SimpleNamespace(text="# reference")])

    @asynccontextmanager
    async def ephemeral(*_: Any, **__: Any) -> AsyncIterator[Client]:
        yield Client()

    with patch("src.infrastructure.mcp.user_pool._ephemeral_client", ephemeral):
        found = await UserMCPClientPool._discover_tools("https://srv.example/mcp", None, 30)

    assert found.has_reference_tool is True
    assert calls == []


# --- the collector -----------------------------------------------------------


async def test_reference_fetched_once_when_domain_selected() -> None:
    pool = FakePool("# Guide")
    with reference_context({"Notes": stored_source("mcp_notes")}), wired(pool):
        first = await collect_user_references(["mcp_notes"], now=NOW)
        second = await collect_user_references(["mcp_notes"], now=NOW + timedelta(seconds=60))

    assert first == second == {"Notes": "# Guide"}
    assert len(pool.calls) == 1


async def test_reference_not_fetched_when_domain_not_selected() -> None:
    pool = FakePool("# Guide")
    with reference_context({"Notes": stored_source("mcp_notes")}), wired(pool):
        found = await collect_user_references(["weather", "mcp_other"], now=NOW)

    assert found == {}
    assert pool.calls == []


async def test_aged_reference_served_then_refreshed() -> None:
    source = stored_source("mcp_notes", reference="# Old", fetched_at=_aged())
    pool = FakePool("# New")
    with reference_context({"Notes": source}), wired(pool) as (background, _publish):
        served = await collect_user_references(["mcp_notes"], now=NOW)
        assert served == {"Notes": "# Old"} and pool.calls == []

        await background.run()
        refreshed = await collect_user_references(["mcp_notes"], now=NOW)

    assert len(pool.calls) == 1
    assert refreshed == {"Notes": "# New"}


async def test_one_refresh_scheduled_while_it_runs() -> None:
    source = stored_source("mcp_notes", reference="# Old", fetched_at=_aged())
    pool = FakePool("# New")
    with reference_context({"Notes": source}), wired(pool) as (background, _publish):
        await collect_user_references(["mcp_notes"], now=NOW)
        await collect_user_references(["mcp_notes"], now=NOW + timedelta(seconds=1))
        assert len(background.pending) == 1
        await background.run()

    assert len(pool.calls) == 1


async def test_fetch_failure_plans_without_reference() -> None:
    before = _count("failed")
    pool = FakePool(RuntimeError("boom"))
    with reference_context({"Notes": stored_source("mcp_notes")}), wired(pool):
        found = await collect_user_references(["mcp_notes"], now=NOW)
        # The attempt is remembered: the next turn does not wait on it again.
        again = await collect_user_references(["mcp_notes"], now=NOW + timedelta(seconds=5))

    assert found == again == {}
    assert len(pool.calls) == 1
    assert _count("failed") == before + 1


async def test_a_worker_without_a_pool_plans_without_reference() -> None:
    """No pool on this worker (shutting down, or never started): a failure, never a raise."""
    before = _count("failed")
    with (
        reference_context({"Notes": stored_source("mcp_notes")}),
        wired(FakePool()),
        patch(f"{MODULE}.get_user_mcp_pool", return_value=None),
    ):
        found = await collect_user_references(["mcp_notes"], now=NOW)

    assert found == {}
    assert _count("failed") == before + 1


async def test_failed_refresh_keeps_the_stored_reference() -> None:
    source = stored_source("mcp_notes", reference="# Old", fetched_at=_aged())
    pool = FakePool(TimeoutError())
    before = _count("timed_out")
    with reference_context({"Notes": source}), wired(pool) as (background, publish):
        await collect_user_references(["mcp_notes"], now=NOW)
        await background.run()
        served = await collect_user_references(["mcp_notes"], now=NOW)

    assert served == {"Notes": "# Old"}
    assert _count("timed_out") == before + 1
    publish.assert_not_awaited()


async def test_fetch_bounded_by_the_dedicated_discovery_timeout() -> None:
    bound = settings.mcp_user_discovery_timeout_seconds
    slow = stored_source("mcp_slow", timeout_seconds=bound * 8)
    quick = stored_source("mcp_quick", timeout_seconds=1)
    pool = FakePool("# A", "# B")
    with reference_context({"Slow": slow, "Quick": quick}), wired(pool):
        await collect_user_references(["mcp_slow", "mcp_quick"], now=NOW)

    timeouts = {server_id: timeout for _user, server_id, timeout in pool.calls}
    assert timeouts == {slow.server_id: bound, quick.server_id: 1}


async def test_claim_held_by_another_worker_skips_the_fetch() -> None:
    source = stored_source("mcp_notes")
    redis = InMemoryRedis()
    redis.store[reference_claim_key(USER_ID, source.server_id)] = "another-worker"
    pool = FakePool("# Guide")
    before = _count("busy")
    with reference_context({"Notes": source}), wired(pool, redis=redis):
        found = await collect_user_references(["mcp_notes"], now=NOW)

    assert found == {}
    assert pool.calls == []
    assert _count("busy") == before + 1


async def test_claim_released_after_the_fetch() -> None:
    source = stored_source("mcp_notes")
    redis = InMemoryRedis()
    with reference_context({"Notes": source}), wired(FakePool("# Guide"), redis=redis):
        await collect_user_references(["mcp_notes"], now=NOW)

    assert reference_claim_key(USER_ID, source.server_id) not in redis.store


async def test_cache_outage_still_fetches() -> None:
    pool = FakePool("# Guide")
    with (
        reference_context({"Notes": stored_source("mcp_notes")}),
        wired(pool, redis=InMemoryRedis(broken=True)),
    ):
        found = await collect_user_references(["mcp_notes"], now=NOW)

    assert found == {"Notes": "# Guide"}


async def test_instructions_served_without_any_fetch() -> None:
    bare = stored_source("mcp_notes", has_reference_tool=False, instructions="Search first.")
    pool = FakePool()
    with reference_context({"Notes": bare}), wired(pool):
        found = await collect_user_references(["mcp_notes"], now=NOW)

    assert found == {"Notes": "Search first."}
    assert pool.calls == []


async def test_instructions_precede_the_reference() -> None:
    both = stored_source(
        "mcp_notes", reference="# Guide", fetched_at=NOW, instructions="Search first."
    )
    with reference_context({"Notes": both}), wired(FakePool()):
        found = await collect_user_references(["mcp_notes"], now=NOW)

    assert found == {"Notes": "Search first.\n\n# Guide"}


async def test_an_empty_read_me_is_not_fetched_again() -> None:
    pool = FakePool(None)
    before = _count("empty")
    with reference_context({"Notes": stored_source("mcp_notes")}), wired(pool):
        first = await collect_user_references(["mcp_notes"], now=NOW)
        second = await collect_user_references(["mcp_notes"], now=NOW + timedelta(seconds=5))

    assert first == second == {}
    assert len(pool.calls) == 1
    assert _count("empty") == before + 1


async def test_no_context_collects_nothing() -> None:
    pool = FakePool()
    with wired(pool):
        assert await collect_user_references(["mcp_notes"], now=NOW) == {}
    assert pool.calls == []


# --- the snapshot ------------------------------------------------------------

TOOLS = [{"name": "read_me", "description": "Guide"}, {"name": "search", "description": "Search"}]


def _entry(**fields: Any) -> PoolEntry:
    return PoolEntry(
        user_id=USER_ID,
        server_id=uuid4(),
        last_used=0.0,
        tools=list(TOOLS),
        catalogue_fingerprint=catalogue_fingerprint(TOOLS),
        configuration_fingerprint="cfg",
        has_reference_tool=True,
        **fields,
    )


def _row(entry: PoolEntry, **snapshot_fields: Any) -> SimpleNamespace:
    fields: dict[str, Any] = {
        "tools": TOOLS,
        "configuration_fingerprint": "cfg",
        "discovered_at": NOW,
        "generation": 7,
        "has_reference_tool": True,
    }
    fields.update(snapshot_fields)
    return SimpleNamespace(
        id=entry.server_id,
        timeout_seconds=30,
        discovered_tools_cache=snapshot_to_jsonb(build_snapshot(**fields)),
    )


async def test_stored_snapshot_reference_served_without_fetch() -> None:
    entry = _entry()
    row = _row(entry, reference_content="# Stored", reference_fetched_at=NOW)
    source = reference_source(row, entry, user_id=USER_ID, domain="mcp_notes")  # type: ignore[arg-type]
    pool = FakePool()
    with reference_context({"Notes": source}), wired(pool):  # type: ignore[dict-item]
        found = await collect_user_references(["mcp_notes"], now=NOW)

    assert found == {"Notes": "# Stored"}
    assert pool.calls == []


async def test_fetched_reference_published_into_the_snapshot_it_describes() -> None:
    entry = _entry()
    source = reference_source(_row(entry), entry, user_id=USER_ID, domain="mcp_notes")  # type: ignore[arg-type]
    with reference_context({"Notes": source}), wired(FakePool("# Guide")) as (_bg, publish):  # type: ignore[dict-item]
        await collect_user_references(["mcp_notes"], now=NOW)

    publish.assert_awaited_once()
    published = publish.await_args.kwargs
    assert (published["user_id"], published["server_id"]) == (USER_ID, entry.server_id)
    assert published["snapshot"].generation == 7
    assert published["snapshot"].reference_content == "# Guide"
    assert published["snapshot"].reference_fetched_at == NOW
    assert published["tool_embeddings"] is None


def test_a_snapshot_of_another_catalogue_is_not_the_source() -> None:
    entry = _entry()
    row = _row(
        entry, tools=[{"name": "other"}], reference_content="# Old", reference_fetched_at=NOW
    )
    source = reference_source(row, entry, user_id=USER_ID, domain="mcp_notes")  # type: ignore[arg-type]
    assert source is not None and source.snapshot is None


def test_a_server_without_guidance_has_no_source() -> None:
    entry = _entry()
    entry.has_reference_tool = False
    assert reference_source(_row(entry), entry, user_id=USER_ID, domain="mcp_x") is None  # type: ignore[arg-type]


# --- registration ------------------------------------------------------------


def _server() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        name="Notes",
        url="https://srv.example/mcp",
        timeout_seconds=30,
        hitl_required=False,
        domain_description="My notes",
        iterative_mode=False,
        auth_type="none",
        discovered_tools_cache=None,
    )


def test_react_catalogue_offers_read_me_pipeline_does_not() -> None:
    from src.infrastructure.mcp.user_context import _register_user_standard_server

    server, ctx = _server(), UserMCPToolsContext()
    entry = _entry()
    _register_user_standard_server(server, entry, USER_ID, ctx, False, {}, "mcp_notes", "abcd1234")  # type: ignore[arg-type]

    def names(mode: str) -> set[str]:
        return {m.name for m in manifests_for_mode(ctx.tool_manifests, mode)}

    assert names(EXECUTION_MODE_REACT) == {"mcp_user_abcd1234_read_me", "mcp_user_abcd1234_search"}
    assert names(EXECUTION_MODE_PIPELINE) == {"mcp_user_abcd1234_search"}
    assert "mcp_user_abcd1234_read_me" in ctx.tool_instances
    assert ctx.server_reference_sources["Notes"].domain == "mcp_notes"


def test_iterative_server_unchanged() -> None:
    from src.infrastructure.mcp.user_context import _register_user_iterative_server

    server, ctx = _server(), UserMCPToolsContext()
    server.iterative_mode = True
    _register_user_iterative_server(server, _entry(), USER_ID, ctx, False, {}, "mcp_notes", "abcd1234")  # type: ignore[arg-type]

    assert ctx.server_domains == {"Notes": "mcp_notes"}
    assert ctx.server_reference_sources == {}


async def test_a_failed_publication_keeps_the_fetched_reference_for_this_turn() -> None:
    """The worker holds the text: a failed write only costs the other workers a fetch."""
    entry = _entry()
    source = reference_source(_row(entry), entry, user_id=USER_ID, domain="mcp_notes")  # type: ignore[arg-type]
    with reference_context({"Notes": source}), wired(FakePool("# Guide")) as (_bg, publish):  # type: ignore[dict-item]
        publish.side_effect = ConnectionError("database down")
        found = await collect_user_references(["mcp_notes"], now=NOW)

    assert found == {"Notes": "# Guide"}
    assert entry.reference_content == "# Guide"
    publish.assert_awaited_once()
