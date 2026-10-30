"""A turn served without the network never queues behind a discovery (fresh review I3).

ADR-366 §3 says the turn never waits for the background revalidation. The revalidation
discovers with ``force_refresh`` through ``get_or_connect``, which held the server's
per-key lock across the network discovery and the wait for a discovery slot — and a
turn's warm or snapshot path sat behind that same lock (reproduced: blocked past 1 s
while a warm entry existed on the worker). The lock now guards the network alone.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.infrastructure.mcp.catalogue_fingerprint import connection_fingerprint
from src.infrastructure.mcp.catalogue_snapshot import build_snapshot, snapshot_to_jsonb
from src.infrastructure.mcp.pool_catalogue import DiscoveredCatalogue
from src.infrastructure.mcp.user_pool import UserMCPClientPool

pytestmark = pytest.mark.unit

_TOOL = {
    "name": "search",
    "description": "Search",
    "input_schema": {},
    "output_schema": None,
    "title": None,
    "annotations": None,
    "app_resource_uri": None,
    "app_visibility": None,
}
_URL = "https://notes.example/mcp"


class _Bench:
    """A pool whose revalidation discovery waits until the test releases it."""

    def __init__(self) -> None:
        self.pool = UserMCPClientPool()
        self.pool._failures = AsyncMock()  # type: ignore[assignment]
        self.pool._failures.remaining = AsyncMock(return_value=0)
        self.pool._cooldowns = AsyncMock()  # type: ignore[assignment]
        self.pool._cooldowns.remaining = AsyncMock(return_value=0)
        self.release = asyncio.Event()
        self.discovering = asyncio.Event()
        self.discoveries = 0

        async def discover(*_a: Any, **_k: Any) -> DiscoveredCatalogue:
            self.discoveries += 1
            if self.discoveries > 1:
                self.discovering.set()
                await self.release.wait()
            return DiscoveredCatalogue(tools=[_TOOL])

        self.pool._discover_tools = discover  # type: ignore[method-assign]
        self.user_id, self.server_id = uuid4(), uuid4()

    def kwargs(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "server_id": self.server_id,
            "url": _URL,
            "auth": None,
            "timeout_seconds": 30,
        }

    async def revalidating(self) -> asyncio.Task[Any]:
        task = asyncio.create_task(self.pool.get_or_connect(**self.kwargs(), force_refresh=True))
        await asyncio.wait_for(self.discovering.wait(), timeout=1.0)
        return task


async def test_a_warm_turn_is_served_while_a_revalidation_discovers() -> None:
    bench = _Bench()
    warm = await bench.pool.get_or_connect(**bench.kwargs())  # the worker's entry
    revalidation = await bench.revalidating()
    try:
        served = await asyncio.wait_for(
            bench.pool.get_or_connect(**bench.kwargs(), stored_catalogue=None), timeout=0.5
        )
        assert served is warm
    finally:
        bench.release.set()
        await revalidation


async def test_a_snapshot_turn_is_hydrated_while_a_revalidation_discovers() -> None:
    bench = _Bench()
    await bench.pool.get_or_connect(**bench.kwargs())
    revalidation = await bench.revalidating()
    bench.pool._entries.clear()  # another worker: no warm entry, the row's snapshot only
    stored = snapshot_to_jsonb(
        build_snapshot(
            tools=[_TOOL],
            configuration_fingerprint=connection_fingerprint(_URL, None, 30, None),
            discovered_at=datetime.now(UTC),
            generation=1,
        )
    )
    try:
        served = await asyncio.wait_for(
            bench.pool.get_or_connect(**bench.kwargs(), stored_catalogue=stored), timeout=0.5
        )
        assert [tool["name"] for tool in served.tools] == ["search"]
    finally:
        bench.release.set()
        await revalidation


async def test_two_turns_needing_the_network_still_discover_once() -> None:
    """The lock still deduplicates the network: the second turn finds the first's entry."""
    bench = _Bench()
    bench.discoveries = -10  # neither discovery waits
    first, second = await asyncio.gather(
        bench.pool.get_or_connect(**bench.kwargs(), stored_catalogue=None),
        bench.pool.get_or_connect(**bench.kwargs(), stored_catalogue=None),
    )
    assert first is second
    assert bench.discoveries == -9


async def test_a_snapshot_never_replaces_a_fresher_discovery_installed_meanwhile() -> None:
    """Third fresh review: the turn's snapshot path awaits Redis outside the lock; a forced
    discovery installing the server's CURRENT catalogue meanwhile (where a tool became
    destructive) was then overwritten by the older, « verified » snapshot."""
    destructive = {**_TOOL, "annotations": {"destructiveHint": True}}
    bench = _Bench()
    bench.discoveries = -10  # the forced discovery answers at once
    bench.pool._discover_tools = AsyncMock(  # type: ignore[method-assign]
        return_value=DiscoveredCatalogue(tools=[destructive])
    )
    gate, entered = asyncio.Event(), asyncio.Event()

    async def slow_pause_check(_key: object) -> int:
        entered.set()
        await gate.wait()
        return 0

    bench.pool._failures.remaining = slow_pause_check
    stored = snapshot_to_jsonb(
        build_snapshot(
            tools=[_TOOL],
            configuration_fingerprint=connection_fingerprint(_URL, None, 30, None),
            discovered_at=datetime.now(UTC),
            generation=1,
        )
    )
    turn = asyncio.create_task(bench.pool.get_or_connect(**bench.kwargs(), stored_catalogue=stored))
    await asyncio.wait_for(entered.wait(), timeout=1.0)
    bench.pool._failures.remaining = AsyncMock(return_value=0)
    fresh = await bench.pool.get_or_connect(**bench.kwargs(), force_refresh=True)
    gate.set()
    served = await turn

    assert bench.pool._entries[(bench.user_id, bench.server_id)] is fresh
    assert served is fresh
