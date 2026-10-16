"""Independent browser-pool owners coordinate against real, isolated Redis keys."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from src.core.config import settings
from src.core.constants import REDIS_KEY_BROWSER_POOL_REGISTRY
from src.infrastructure.browser import coordination
from src.infrastructure.browser import pool as module
from src.infrastructure.browser.errors import BrowserRefusal, BrowserRefusalReason
from src.infrastructure.browser.models import BrowserSessionInfo
from src.infrastructure.cache import redis as cache_module

pytestmark = pytest.mark.integration


class _Namespace:
    """Change keys only; all admission and ownership decisions still run in Redis."""

    def __init__(self, client: Redis, prefix: str) -> None:
        self.client = client
        self.prefix = prefix
        self.down = False

    def _key(self, value: str) -> str:
        if self.down:
            raise RedisConnectionError("test Redis unavailable")
        return self.prefix + value

    async def get(self, key: str) -> Any:
        return await self.client.get(self._key(key))

    async def set(self, key: str, value: Any, **kwargs: Any) -> Any:
        return await self.client.set(self._key(key), value, **kwargs)

    async def keys(self, pattern: str) -> list[str]:
        keys = await self.client.keys(self._key(pattern))
        return [key[len(self.prefix) :] for key in keys]

    async def delete(self, *keys: str) -> Any:
        return await self.client.delete(*(self._key(key) for key in keys))

    async def eval(self, script: str, count: int, *args: Any) -> Any:
        keys = [self._key(key) for key in args[:count]]
        return await self.client.eval(script, count, *keys, *args[count:])


class _Session:
    is_busy = False

    def __init__(self, *, user_id: str, context: Any, security: Any) -> None:
        self.user_id = user_id
        self.context = context
        self.last_activity = time.monotonic()
        self.navigation_count = 0
        self.navigations: list[str] = []

    async def navigate(self, url: str) -> None:
        self.navigations.append(url)
        self.navigation_count += 1

    async def close(self) -> None:
        await self.context.close()


@dataclass
class _World:
    namespace: _Namespace
    pools: list[module.BrowserPool]


@pytest.fixture
async def world(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_World]:
    redis = Redis.from_url(str(settings.redis_url), decode_responses=True)
    await redis.ping()
    prefix = f"test:browser-pool:{uuid4().hex}:"
    namespace = _Namespace(redis, prefix)

    async def cache() -> Any:
        return namespace

    monkeypatch.setattr(cache_module, "get_redis_cache", cache)
    monkeypatch.setattr(settings, "browser_max_concurrent_sessions", 1)
    monkeypatch.setattr("src.infrastructure.browser.session.BrowserSession", _Session)
    pools = [module.BrowserPool() for _ in range(3)]
    for index, pool in enumerate(pools):
        pool._pid = index + 1000
        pool._healthy = True
        context = AsyncMock()
        pool._browser = AsyncMock()
        pool._browser.new_context.return_value = context
    try:
        yield _World(namespace, pools)
    finally:
        for pool in pools:
            await pool.close()
        keys = [key async for key in redis.scan_iter(match=f"{prefix}*")]
        if keys:
            await redis.delete(*keys)
        await redis.aclose()


async def _acquire(pool: module.BrowserPool, user: str) -> Any:
    try:
        return await pool.acquire_session(user)
    except BrowserRefusal as exc:
        return exc


async def test_an_allocating_context_already_occupies_the_last_global_slot(world: _World) -> None:
    first, second, _ = world.pools
    entered, release = asyncio.Event(), asyncio.Event()
    context = first._browser.new_context.return_value

    async def allocating(**kwargs: Any) -> Any:
        entered.set()
        await release.wait()
        return context

    first._browser.new_context.side_effect = allocating
    creating = asyncio.create_task(first.acquire_session(uuid4().hex))
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        outcome = await asyncio.wait_for(_acquire(second, uuid4().hex), timeout=2)
    finally:
        release.set()
        await creating

    assert isinstance(outcome, BrowserRefusal)
    assert outcome.reason is BrowserRefusalReason.CAPACITY
    second._browser.new_context.assert_not_awaited()


@pytest.mark.parametrize("late_action", ["release", "update"])
async def test_a_previous_owner_cannot_erase_or_overwrite_the_recovered_session(
    world: _World, late_action: str
) -> None:
    first, second, third = world.pools
    user = uuid4().hex
    await first.acquire_session(user)
    await first.update_session_redis(user, "https://first.example/page", "First")
    await second.acquire_session(user)
    await second.update_session_redis(user, "https://current.example/page", "Current")

    if late_action == "release":
        await first.release_session(user)
    else:
        await first.update_session_redis(user, "https://stale.example/page", "Stale")
    recovered = await third.acquire_session(user)

    assert recovered.navigations == ["https://current.example/page"]


async def test_a_worker_pid_reused_after_restart_does_not_hide_recovery(world: _World) -> None:
    first, second, _ = world.pools
    second._pid = first._pid
    user = uuid4().hex
    await first.acquire_session(user)
    await first.update_session_redis(user, "https://current.example/page", "Current")

    recovered = await second.acquire_session(user)

    assert recovered.navigations == ["https://current.example/page"]


async def test_redis_outage_preserves_availability_with_a_local_bound(world: _World) -> None:
    world.namespace.down = True
    first = world.pools[0]
    assert isinstance(await first.acquire_session(uuid4().hex), _Session)

    outcome = await _acquire(first, uuid4().hex)

    assert isinstance(outcome, BrowserRefusal)
    assert outcome.reason is BrowserRefusalReason.CAPACITY
    assert first._browser.new_context.await_count == 1


async def test_shutdown_drains_a_context_whose_allocation_was_already_in_flight(
    world: _World,
) -> None:
    pool = world.pools[0]
    entered, release = asyncio.Event(), asyncio.Event()
    context = pool._browser.new_context.return_value

    async def allocating(**kwargs: Any) -> Any:
        entered.set()
        await release.wait()
        return context

    pool._browser.new_context.side_effect = allocating
    creating = asyncio.create_task(pool.acquire_session(uuid4().hex))
    await asyncio.wait_for(entered.wait(), timeout=2)
    closing = asyncio.create_task(pool.close())
    try:
        await asyncio.sleep(0)
    finally:
        release.set()
        await asyncio.gather(creating, closing)

    assert not pool._sessions
    assert not pool.is_healthy
    assert pool._maintenance_task is None
    context.close.assert_awaited_once()


@pytest.mark.parametrize("loss", ["takeover", "expiry"])
async def test_an_allocation_that_lost_ownership_is_closed_before_it_can_be_lent(
    world: _World, monkeypatch: pytest.MonkeyPatch, loss: str
) -> None:
    if loss == "expiry":
        # Scale the real Redis deadline down, preserving its integer-second shape.
        monkeypatch.setattr(settings, "browser_session_timeout_seconds", 1)
    first, second, _ = world.pools
    user = uuid4().hex
    entered, release = asyncio.Event(), asyncio.Event()
    context = first._browser.new_context.return_value

    async def allocating(**kwargs: Any) -> Any:
        entered.set()
        await release.wait()
        return context

    first._browser.new_context.side_effect = allocating
    creating = asyncio.create_task(_acquire(first, user))
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        if loss == "expiry":
            await asyncio.sleep(1.1)
        await second.acquire_session(user if loss == "takeover" else uuid4().hex)
    finally:
        release.set()
        outcome = await creating

    assert isinstance(outcome, BrowserRefusal)
    assert outcome.reason.code == "DEPENDENCY_ERROR"
    assert user not in first._sessions
    context.close.assert_awaited_once()


async def test_hostile_page_metadata_stays_bounded_without_recovering_a_cut_url(
    world: _World,
) -> None:
    first, second, _ = world.pools
    user = uuid4().hex
    await first.acquire_session(user)
    await first.update_session_redis(
        user, "https://current.example/" + "a" * 1_000_000, "T" * 1_000_000
    )

    used = await world.namespace.client.memory_usage(
        world.namespace.prefix + REDIS_KEY_BROWSER_POOL_REGISTRY
    )
    assert used is not None and used < 65_536
    recovered = await second.acquire_session(user)
    assert len(recovered.navigations) == 0


async def test_each_worker_retires_its_own_idle_context_and_joins_maintenance(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(module, "BROWSER_SESSION_MAINTENANCE_INTERVAL_SECONDS", 0.01)
    pool = world.pools[1]
    user = uuid4().hex
    session = await pool.acquire_session(user)
    maintenance = pool._maintenance_task
    assert maintenance is not None
    session.last_activity = time.monotonic() - settings.browser_session_timeout_seconds - 1

    await asyncio.wait_for(maintenance, timeout=3)

    assert user not in pool._sessions
    assert user not in pool._session_info
    session.context.close.assert_awaited_once()
    assert pool._maintenance_task is None


async def test_a_superseded_context_is_retired_without_erasing_the_new_owner(world: _World) -> None:
    first, second, third = world.pools
    user = uuid4().hex
    old = await first.acquire_session(user)
    await second.acquire_session(user)
    await second.update_session_redis(user, "https://current.example/page", "Current")

    await first.cleanup_expired()

    old.context.close.assert_awaited_once()
    assert user not in first._sessions
    recovered = await third.acquire_session(user)
    assert recovered.navigations == ["https://current.example/page"]


async def test_redis_recovery_retires_an_offline_context_without_claiming_another_users_slot(
    world: _World,
) -> None:
    first, second, _ = world.pools
    world.namespace.down = True
    user = uuid4().hex
    offline = await first.acquire_session(user)
    world.namespace.down = False
    current_user = uuid4().hex
    current = await second.acquire_session(current_user)

    await first.cleanup_expired()

    offline.context.close.assert_awaited_once()
    assert user not in first._sessions
    assert await second.acquire_session(current_user) is current


@pytest.mark.parametrize("stage", ["legacy_recovery", "context_allocation"])
async def test_cancelled_admission_releases_its_unpublished_global_slot(
    world: _World, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    first, second, _ = world.pools
    user = uuid4().hex
    entered = asyncio.Event()

    async def blocked(*args: Any, **kwargs: Any) -> Any:
        entered.set()
        await asyncio.Event().wait()

    if stage == "legacy_recovery":
        monkeypatch.setattr(first, "_get_recovery_url", blocked)
    else:
        first._browser.new_context.side_effect = blocked
    creating = asyncio.create_task(first.acquire_session(user))
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
    finally:
        creating.cancel()
        with pytest.raises(asyncio.CancelledError):
            await creating

    assert user not in first._sessions
    assert user not in first._session_info
    assert isinstance(await second.acquire_session(uuid4().hex), _Session)


@pytest.mark.parametrize("access", ["renew", "no_request"])
async def test_expired_private_metadata_does_not_survive_another_users_activity(
    world: _World, monkeypatch: pytest.MonkeyPatch, access: str
) -> None:
    monkeypatch.setattr(settings, "browser_max_concurrent_sessions", 2)
    monkeypatch.setattr(settings, "browser_session_timeout_seconds", 1)
    first, second, _ = world.pools
    old_user, current_user = uuid4().hex, uuid4().hex
    await first.acquire_session(old_user)
    await first.update_session_redis(old_user, "https://private.example/expired", "Expired")
    maintenance = first._maintenance_task
    assert maintenance is not None
    maintenance.cancel()  # This worker no longer renews its metadata.
    with pytest.raises(asyncio.CancelledError):
        await maintenance
    monkeypatch.setattr(settings, "browser_session_timeout_seconds", 300)
    await second.acquire_session(current_user)
    await asyncio.sleep(1.1)

    if access == "renew":
        assert await second._owns_session(current_user) is True

    key = world.namespace.prefix + REDIS_KEY_BROWSER_POOL_REGISTRY
    assert await world.namespace.client.hexists(key, old_user) == 0


async def test_recovery_round_trips_every_serialized_metadata_field(world: _World) -> None:
    user = uuid4().hex
    previous = BrowserSessionInfo(
        session_id=uuid4().hex,
        user_id=user,
        created_at=datetime.now(UTC),
        current_url="https://example.test/page?q=%E4%B8%AD#part",
        page_title="标题 – Café",
        worker_pid=123,
        navigation_count=7,
    )
    assert await coordination.reserve(user, previous) is None
    following = previous.model_copy(update={"session_id": uuid4().hex, "worker_pid": 456})

    assert await coordination.reserve(user, following) == previous
