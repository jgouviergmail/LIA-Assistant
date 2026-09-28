"""One radio per worker: built once on first use, its loops stopped within a bound (ADR-324)."""

from __future__ import annotations

import pytest

from src.domains.radio import wiring
from src.domains.radio.constants import LOOP_STOP_TIMEOUT_S, NEWSROOM_REQUEST_TIMEOUT_S
from tests.unit.domains.radio.fakes import FakeRedis

pytestmark = pytest.mark.unit


@pytest.fixture
def fresh(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """A worker that has not built its radio yet; counts the cache reads."""
    reads: list[int] = []
    redis = FakeRedis()

    async def cache() -> FakeRedis:
        reads.append(1)
        return redis

    monkeypatch.setattr(wiring, "_built", None)
    monkeypatch.setattr(wiring, "get_redis_cache", cache)
    return reads


async def test_the_radio_is_built_once_whoever_asks_first(fresh: list[int]) -> None:
    service = await wiring.radio_service()
    robots = await wiring.newsroom_robots()

    assert await wiring.radio_service() is service
    assert await wiring.newsroom_robots() is robots
    assert len(fresh) == 1


async def test_a_worker_that_never_aired_has_nothing_to_stop(fresh: list[int]) -> None:
    await wiring.stop_radio_loops()

    assert fresh == []  # stopping builds nothing


async def test_the_shutdown_waits_for_the_loops_within_the_bound(
    fresh: list[int], monkeypatch: pytest.MonkeyPatch
) -> None:
    await wiring.radio_service()
    built = wiring._built
    assert built is not None
    asked: list[float | None] = []

    async def stop_all(*, timeout_s: float | None = None) -> None:
        asked.append(timeout_s)

    monkeypatch.setattr(built.launcher, "stop_all", stop_all)

    await wiring.stop_radio_loops()

    assert asked == [LOOP_STOP_TIMEOUT_S]


async def test_a_newsroom_client_is_bounded_and_closed_when_its_block_ends() -> None:
    async with wiring.newsroom_client() as client:
        assert client.timeout.connect == NEWSROOM_REQUEST_TIMEOUT_S
        assert client.timeout.read == NEWSROOM_REQUEST_TIMEOUT_S
        assert client.follow_redirects is False  # the fetch checks every hop itself

    assert client.is_closed
