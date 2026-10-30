"""An aged personal catalogue is revalidated in the background, once, and only published if current.

Spec 2026-10-21 §5.4 (M2). The real pool and the real claim primitive run; the
row, the network, the failure pause, the cache and the publication are doubles.
Two independent actors on one claim, the database fence and a stale completion
are proven on real Redis and PostgreSQL in
``tests/integration/infrastructure/mcp_catalogue/test_revalidation_claim.py``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from src.core.time_utils import now_utc
from src.infrastructure.llm.embedding_context import get_embedding_context
from src.infrastructure.mcp.catalogue_fingerprint import connection_fingerprint
from src.infrastructure.mcp.catalogue_revalidation import (
    revalidate_catalogue,
    revalidation_claim_key,
    schedule_catalogue_revalidation,
)
from src.infrastructure.mcp.catalogue_snapshot import build_snapshot, snapshot_to_jsonb
from src.infrastructure.mcp.user_pool import DiscoveredCatalogue, UserMCPClientPool
from src.infrastructure.observability.metrics_mcp import mcp_user_catalogue_revalidations_total
from tests.helpers.redis_double import InMemoryRedis

pytestmark = pytest.mark.unit

MODULE = "src.infrastructure.mcp.catalogue_revalidation"
OLD = [{"name": "search", "description": "Search", "input_schema": {}}]
NEW = [{"name": "reconcile", "description": "Reconcile", "input_schema": {}}]


class Failures:
    def __init__(self) -> None:
        self.paused: float = 0.0
        self.recorded = 0
        self.cleared = 0

    async def remaining(self, key: tuple[UUID, UUID]) -> float:
        return self.paused

    async def record(self, key: tuple[UUID, UUID]) -> float:
        self.recorded += 1
        return 30.0

    async def clear(self, key: tuple[UUID, UUID]) -> None:
        self.cleared += 1


class Bench:
    """One row, one worker's pool, the network's answer and what was published."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.user_id = uuid4()
        self.row = SimpleNamespace(
            id=uuid4(),
            user_id=self.user_id,
            name="Notes",
            url="https://notes.example/mcp",
            timeout_seconds=30,
            extra_headers=None,
            is_enabled=True,
            status="active",
            discovered_tools_cache=self.stored(OLD),
        )
        self.answer: list[dict[str, Any]] | BaseException = NEW
        self.discoveries = 0
        self.failures = Failures()
        self.pool = UserMCPClientPool(failures=self.failures)  # type: ignore[arg-type]
        self.pool._raise_if_cooling = AsyncMock()  # type: ignore[method-assign]
        self.pool._discover_tools = self.discover  # type: ignore[method-assign]
        self.redis = InMemoryRedis()
        self.publish = AsyncMock(return_value="published")
        self.attributed: list[str | None] = []
        self.load = AsyncMock(return_value=self.row)
        monkeypatch.setattr(f"{MODULE}._load", self.load)
        monkeypatch.setattr(f"{MODULE}.get_user_mcp_pool", lambda: self.pool)
        monkeypatch.setattr(f"{MODULE}.get_redis_cache", AsyncMock(side_effect=lambda: self.redis))
        monkeypatch.setattr(f"{MODULE}.build_auth_for_server", lambda row: None)
        monkeypatch.setattr(f"{MODULE}.publish_catalogue_if_current", self.publish)
        monkeypatch.setattr(f"{MODULE}.usable_tool_embeddings", AsyncMock(side_effect=self.embed))

    def stored(self, tools: list[dict[str, Any]]) -> dict[str, Any]:
        return snapshot_to_jsonb(
            build_snapshot(
                tools=tools,
                configuration_fingerprint=connection_fingerprint(
                    "https://notes.example/mcp", None, 30, None
                ),
                discovered_at=now_utc(),
                generation=1,
            )
        )

    async def discover(self, url: str, auth: object, timeout: int, **_: Any) -> Any:
        self.discoveries += 1
        if isinstance(self.answer, BaseException):
            raise self.answer
        return DiscoveredCatalogue(tools=list(self.answer))

    async def embed(self, server: Any, tools: Any) -> dict[str, Any]:
        context = get_embedding_context()
        self.attributed.append(context.user_id if context else None)
        return {}

    async def run(self) -> str:
        return await revalidate_catalogue(self.user_id, self.row.id)

    @property
    def key(self) -> str:
        return revalidation_claim_key(self.user_id, self.row.id)


@pytest.fixture
def bench(monkeypatch: pytest.MonkeyPatch) -> Iterator[Bench]:
    yield Bench(monkeypatch)


def _count(outcome: str) -> float:
    return mcp_user_catalogue_revalidations_total.labels(outcome=outcome)._value.get()


async def test_revalidation_publishes_a_fresh_discovery(bench: Bench) -> None:
    before = _count("published")

    assert await bench.run() == "published"

    entry = bench.pool._entries[(bench.user_id, bench.row.id)]
    assert [tool["name"] for tool in entry.tools] == ["reconcile"]  # this worker's entry replaced
    snapshot = bench.publish.await_args.kwargs["snapshot"]
    assert snapshot.generation == entry.generation and snapshot.tools[0]["name"] == "reconcile"
    assert bench.key not in bench.redis.store  # released by its owner
    assert bench.failures.cleared == 1 and _count("published") == before + 1


async def test_vectors_only_when_the_catalogue_changed(bench: Bench) -> None:
    await bench.run()
    assert bench.attributed == [str(bench.user_id)]  # embedded, attributed to the account

    bench.answer = OLD  # unchanged against the stored snapshot
    bench.attributed.clear()
    await bench.run()
    assert bench.attributed == []


@pytest.fixture
def short_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    """A one-second claim, so a slow step outlives it within the test."""
    monkeypatch.setattr(f"{MODULE}._CLAIM_MARGIN_SECONDS", 1)
    monkeypatch.setattr("src.core.config.settings.mcp_user_discovery_timeout_seconds", 0)


@pytest.mark.usefixtures("short_claim")
async def test_a_revalidation_longer_than_its_claim_keeps_it(bench: Bench) -> None:
    """The slot wait and the embedding outlived the claim: a second worker revalidated beside it."""
    seen: list[str | None] = []

    async def slow_embed(server: Any, tools: Any) -> dict[str, Any]:
        await asyncio.sleep(1.5)  # past the one-second claim
        seen.append(bench.redis.store.get(bench.key))
        return {}

    usable = AsyncMock(side_effect=slow_embed)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(f"{MODULE}.usable_tool_embeddings", usable)
        assert await bench.run() == "published"

    assert bench.redis.refreshes >= 1 and seen and seen[0] is not None
    assert bench.key not in bench.redis.store  # released by its owner


@pytest.mark.usefixtures("short_claim")
async def test_a_revalidation_that_lost_its_claim_says_so(bench: Bench) -> None:
    before = _count("claim_lost")

    async def taken_over(server: Any, tools: Any) -> dict[str, Any]:
        bench.redis.store[bench.key] = "successor"  # another worker holds it now
        await asyncio.sleep(5)  # stopped at the keeper's next refresh
        return {}

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(f"{MODULE}.usable_tool_embeddings", AsyncMock(side_effect=taken_over))
        assert await bench.run() == "claim_lost"

    assert _count("claim_lost") == before + 1
    assert bench.redis.store[bench.key] == "successor"  # never released for someone else


async def test_busy_claim_skips(bench: Bench) -> None:
    bench.redis.store[bench.key] = "another-worker"
    before = _count("busy")

    assert await bench.run() == "busy"
    assert bench.discoveries == 0 and _count("busy") == before + 1
    assert bench.redis.store[bench.key] == "another-worker"


async def test_without_the_cache_it_does_not_run(bench: Bench) -> None:
    bench.redis = InMemoryRedis(broken=True)

    assert await bench.run() == "claim_unavailable"
    assert bench.discoveries == 0


async def test_a_paused_server_is_left_alone(bench: Bench) -> None:
    bench.failures.paused = 42.0

    assert await bench.run() == "paused"
    assert bench.discoveries == 0 and bench.key not in bench.redis.store


@pytest.mark.parametrize(
    ("change", "outcome"),
    [({"is_enabled": False}, "inactive"), ({"status": "error"}, "inactive"), (None, "missing")],
)
async def test_an_inactive_or_missing_row_is_left_alone(
    bench: Bench, change: dict[str, Any] | None, outcome: str
) -> None:
    if change is None:
        bench.load.return_value = None
    else:
        for name, value in change.items():
            setattr(bench.row, name, value)

    assert await bench.run() == outcome
    assert bench.discoveries == 0


async def test_a_failure_feeds_the_pause(bench: Bench) -> None:
    bench.answer = RuntimeError("down")

    assert await bench.run() == "failed"
    assert bench.failures.recorded == 1
    bench.publish.assert_not_awaited()
    assert bench.key not in bench.redis.store


async def test_a_timeout_is_counted_apart(bench: Bench) -> None:
    bench.answer = TimeoutError()

    assert await bench.run() == "timed_out"


async def test_a_refused_publication_counts_its_reason(bench: Bench) -> None:
    bench.publish.return_value = "configuration_changed"

    assert await bench.run() == "configuration_changed"
    assert bench.attributed == []  # nothing published, no vectors


async def test_scheduling_hands_the_work_to_the_background_set(
    bench: Bench, monkeypatch: pytest.MonkeyPatch
) -> None:
    owned: list[Any] = []
    monkeypatch.setattr(f"{MODULE}.safe_fire_and_forget", lambda coro, **_: owned.append(coro))

    schedule_catalogue_revalidation(bench.user_id, bench.row.id)

    assert len(owned) == 1 and await owned[0] == "published"


async def test_a_worker_without_a_pool_revalidates_nothing(
    bench: Bench, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(f"{MODULE}.get_user_mcp_pool", lambda: None)
    before = _count("failed")

    assert await bench.run() == "failed"
    assert bench.discoveries == 0
    bench.publish.assert_not_awaited()
    assert _count("failed") == before + 1
