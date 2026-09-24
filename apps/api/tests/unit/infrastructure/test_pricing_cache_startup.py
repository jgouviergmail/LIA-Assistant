"""Which source each path of the pricing cache trusts.

A worker keeps its in-memory prices for its whole life, so what it loads at
STARTUP is what it bills with until an administrator edits a tariff. It used to
start from the Redis blob when one existed — and a blob written before a
deploy's pricing migration still carries the old tariffs: measured on Docker dev
2026-09-23, the API restarted after the DeepSeek weekday migration and kept
billing Saturday peak hours at double from a 47-minute-old blob.

Startup therefore rebuilds from the database; only the cross-worker
invalidation (ADR-063) adopts the blob, because there a peer has JUST rebuilt
and published it.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.infrastructure.cache import pricing_cache
from src.infrastructure.cache.pricing_cache import (
    CachedModelPrice,
    PricingCacheData,
    PricingCacheService,
)

pytestmark = pytest.mark.unit

_STALE = PricingCacheData(
    models={
        "deepseek-flash": CachedModelPrice(
            input_unit_price=0.15, output_unit_price=0.6, cached_input_unit_price=0.003
        )
    },
    usd_eur_rate=0.9,
    last_refresh_ts=0.0,
)
_FROM_DATABASE = PricingCacheData(
    models={
        "deepseek-flash": CachedModelPrice(
            input_unit_price=0.15,
            output_unit_price=0.6,
            cached_input_unit_price=0.003,
            time_slots=[
                {
                    "start_utc": "01:00",
                    "end_utc": "04:00",
                    "input_unit_price": 0.3,
                    "cached_input_unit_price": 0.006,
                    "output_unit_price": 1.2,
                    "weekdays": [1, 2, 3, 4, 5],
                }
            ],
        )
    },
    usd_eur_rate=0.9,
    last_refresh_ts=1.0,
)


class _FakeRedis:
    """Holds one blob, like the pricing key of the shared Redis."""

    def __init__(self, blob: str | None) -> None:
        self.blob = blob

    async def get(self, key: str) -> str | None:
        return self.blob

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.blob = value

    async def delete(self, key: str) -> None:
        self.blob = None


@pytest.fixture(autouse=True)
def _restore_local_cache() -> Iterator[None]:
    before = pricing_cache._local_cache
    pricing_cache._local_cache = None
    yield
    pricing_cache._local_cache = before


@pytest.fixture
def database_reads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Stand in for the database read: records each rebuild and installs its prices."""
    reads: list[str] = []

    async def fake_refresh(self: PricingCacheService) -> bool:
        reads.append("database")
        pricing_cache._local_cache = _FROM_DATABASE
        await self.redis.set("key", _FROM_DATABASE.to_json())
        return True

    monkeypatch.setattr(PricingCacheService, "refresh_from_database", fake_refresh)
    return reads


def _redis(monkeypatch: pytest.MonkeyPatch, blob: str | None) -> _FakeRedis:
    redis = _FakeRedis(blob)

    async def fake_get_redis_cache() -> _FakeRedis:
        return redis

    monkeypatch.setattr("src.infrastructure.cache.redis.get_redis_cache", fake_get_redis_cache)
    return redis


async def test_startup_rebuilds_from_the_database_even_over_a_blob(
    monkeypatch: pytest.MonkeyPatch, database_reads: list[str]
) -> None:
    _redis(monkeypatch, _STALE.to_json())

    assert await pricing_cache.refresh_pricing_cache() is True

    assert database_reads == ["database"]
    price = pricing_cache.get_cached_model_price("deepseek-flash")
    assert price is not None and price.time_slots is not None
    assert price.time_slots[0]["weekdays"] == [1, 2, 3, 4, 5]


async def test_an_invalidation_adopts_the_blob_a_peer_just_published(
    monkeypatch: pytest.MonkeyPatch, database_reads: list[str]
) -> None:
    """The writer rebuilt and published before notifying: its blob is the
    fresh one, and N workers need not re-read the table."""
    _redis(monkeypatch, _FROM_DATABASE.to_json())

    assert await pricing_cache.load_published_pricing_cache() is True

    assert database_reads == []
    price = pricing_cache.get_cached_model_price("deepseek-flash")
    assert price is not None and price.time_slots is not None


async def test_an_invalidation_with_no_blob_left_rebuilds(
    monkeypatch: pytest.MonkeyPatch, database_reads: list[str]
) -> None:
    _redis(monkeypatch, None)

    assert await pricing_cache.load_published_pricing_cache() is True

    assert database_reads == ["database"]


async def test_startup_falls_back_to_the_published_blob_when_the_database_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A worker whose database read fails at boot would price every call at
    ZERO for its whole life — an older published blob prices them better."""

    async def failing_refresh(self: PricingCacheService) -> bool:
        return False

    monkeypatch.setattr(PricingCacheService, "refresh_from_database", failing_refresh)
    _redis(monkeypatch, _STALE.to_json())

    assert await pricing_cache.refresh_pricing_cache() is True

    assert pricing_cache.get_cached_model_price("deepseek-flash") is not None


async def test_a_rebuild_tells_the_other_workers_and_a_failed_one_does_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-063: a writer reloads, THEN publishes — the other workers adopt the
    blob it just wrote. Publishing after a failed reload would make them adopt
    a blob that says nothing new."""
    published: list[str] = []

    async def record(cache_name: str) -> None:
        published.append(cache_name)

    monkeypatch.setattr("src.infrastructure.cache.invalidation.publish_cache_invalidation", record)
    outcome = {"ok": True}

    async def refresh(self: PricingCacheService) -> bool:
        return outcome["ok"]

    monkeypatch.setattr(PricingCacheService, "refresh_from_database", refresh)
    service = PricingCacheService(_FakeRedis(None))  # type: ignore[arg-type]

    assert await service.invalidate_and_refresh() is True
    outcome["ok"] = False
    assert await service.invalidate_and_refresh() is False

    assert published == ["pricing"]
