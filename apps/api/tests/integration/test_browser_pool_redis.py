"""Independent browser-pool owners coordinate against real, isolated Redis keys."""

from __future__ import annotations

import asyncio
import json
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

from src.core.browser_scope import BrowserScope
from src.core.config import settings
from src.core.constants import REDIS_KEY_BROWSER_POOL_REGISTRY
from src.domains.agents.context.runtime_context import LiaRuntimeContext, derive_sub_agent_context
from src.domains.agents.tools.browser_tools import _get_session
from src.infrastructure.browser import coordination
from src.infrastructure.browser import pool as module
from src.infrastructure.browser.errors import BrowserRefusal, BrowserRefusalReason
from src.infrastructure.browser.models import BrowserSessionInfo
from src.infrastructure.cache import redis as cache_module
from tests.fixtures.browser_scope import browser_scope
from tests.helpers.runtime_context import make_tool_runtime

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

    def __init__(self, *, scope: BrowserScope, context: Any, security: Any) -> None:
        self.scope = scope
        self.user_id = str(scope.owner_id)
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


async def _acquire(pool: module.BrowserPool, user: BrowserScope) -> Any:
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
    creating = asyncio.create_task(first.acquire_session(browser_scope()))
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        outcome = await asyncio.wait_for(_acquire(second, browser_scope()), timeout=2)
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
    user = browser_scope()
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
    user = browser_scope()
    await first.acquire_session(user)
    await first.update_session_redis(user, "https://current.example/page", "Current")

    recovered = await second.acquire_session(user)

    assert recovered.navigations == ["https://current.example/page"]


async def test_redis_outage_preserves_availability_with_a_local_bound(world: _World) -> None:
    world.namespace.down = True
    first = world.pools[0]
    assert isinstance(await first.acquire_session(browser_scope()), _Session)

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
    creating = asyncio.create_task(pool.acquire_session(browser_scope()))
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
    user = browser_scope()
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
        await second.acquire_session(user if loss == "takeover" else browser_scope())
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
    user = browser_scope()
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
    user = browser_scope()
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
    user = browser_scope()
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
    user = browser_scope()
    offline = await first.acquire_session(user)
    world.namespace.down = False
    current_user = browser_scope()
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
    user = browser_scope()
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
    assert isinstance(await second.acquire_session(browser_scope()), _Session)


@pytest.mark.parametrize("access", ["renew", "no_request"])
async def test_expired_private_metadata_does_not_survive_another_users_activity(
    world: _World, monkeypatch: pytest.MonkeyPatch, access: str
) -> None:
    monkeypatch.setattr(settings, "browser_max_concurrent_sessions", 2)
    monkeypatch.setattr(settings, "browser_session_timeout_seconds", 1)
    first, second, _ = world.pools
    old_user, current_user = browser_scope(), browser_scope()
    await first.acquire_session(old_user)
    await first.update_session_redis(old_user, "https://private.example/expired", "Expired")
    maintenance = first._maintenance_task
    assert maintenance is not None
    maintenance.cancel()  # This worker no longer renews its metadata.
    with pytest.raises(asyncio.CancelledError):
        await maintenance
    client = world.namespace.client
    key = world.namespace.prefix + REDIS_KEY_BROWSER_POOL_REGISTRY
    deadline = json.loads(await client.hget(key, old_user.key))["expires_ms"]
    assert await client.execute_command("HPEXPIRETIME", key, "FIELDS", 1, old_user.key) == [
        deadline
    ]
    monkeypatch.setattr(settings, "browser_session_timeout_seconds", 300)
    await second.acquire_session(current_user)
    # Another user's activity must preserve the original field deadline. An
    # already-expired field is also valid if context allocation took longer.
    assert await client.execute_command("HPEXPIRETIME", key, "FIELDS", 1, old_user.key) in (
        [deadline],
        [-2],
    )
    # Redis TIME owns the deadline, not the host running pytest (Docker/WSL
    # may have a different wall clock). Do not let a host sleep stand in for
    # observing expiry, nor let a missing native TTL hide behind Lua pruning.
    async with asyncio.timeout(5):
        while True:
            seconds, microseconds = await client.time()
            if seconds * 1000 + microseconds // 1000 > deadline:
                break
            await asyncio.sleep(0.05)

    if access == "renew":
        assert await second._owns_session(current_user) is True

    assert await client.hexists(key, old_user.key) == 0


async def test_recovery_round_trips_every_serialized_metadata_field(world: _World) -> None:
    user = browser_scope()
    previous = BrowserSessionInfo(
        session_id=uuid4().hex,
        user_id=str(user.owner_id),
        runtime_id=user.runtime_id,
        created_at=datetime.now(UTC),
        current_url="https://example.test/page?q=%E4%B8%AD#part",
        page_title="标题 – Café",
        worker_pid=123,
        navigation_count=7,
    )
    assert await coordination.reserve(user, previous) is None
    following = previous.model_copy(update={"session_id": uuid4().hex, "worker_pid": 456})

    assert await coordination.reserve(user, following) == previous


async def test_two_discussions_get_distinct_browser_contexts_and_child_reuses_root(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tool-result isolation must extend to the actual browser-session allocation."""
    monkeypatch.setattr(settings, "browser_max_concurrent_sessions", 3)
    pool = world.pools[0]
    monkeypatch.setattr(module, "get_browser_pool", AsyncMock(return_value=pool))
    pool._browser.new_context.side_effect = [AsyncMock(), AsyncMock()]
    owner, runtime_a, runtime_b = uuid4(), uuid4(), uuid4()
    context_a = LiaRuntimeContext(
        user_id=owner,
        conversation_id=str(uuid4()),
        thread_id=str(runtime_a),
        runtime_id=runtime_a,
        conversation_revision=1,
    )
    context_b = LiaRuntimeContext(
        user_id=owner,
        conversation_id=str(uuid4()),
        thread_id=str(runtime_b),
        runtime_id=runtime_b,
        conversation_revision=1,
    )
    _, first = await _get_session(make_tool_runtime(context=context_a), str(owner))
    _, second = await _get_session(make_tool_runtime(context=context_b), str(owner))
    _, child = await _get_session(
        make_tool_runtime(context=derive_sub_agent_context(context_a, thread_id="browser-child")),
        str(owner),
    )
    assert first is not second
    assert isinstance(first, _Session) and isinstance(second, _Session)
    assert first.context is not second.context
    assert child is first
    assert pool._browser.new_context.await_count == 2


async def test_browser_without_declared_runtime_cannot_fall_back_to_account_session(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool = world.pools[0]
    monkeypatch.setattr(module, "get_browser_pool", AsyncMock(return_value=pool))
    context = LiaRuntimeContext(user_id=uuid4(), thread_id="unknown", conversation_id="unknown")
    with pytest.raises(BrowserRefusal):
        await _get_session(make_tool_runtime(context=context), str(context.user_id))
    pool._browser.new_context.assert_not_awaited()


async def test_another_discussion_of_same_account_consumes_global_capacity(world: _World) -> None:
    owner = uuid4()
    await world.pools[0].acquire_session(BrowserScope(owner, uuid4()))
    with pytest.raises(BrowserRefusal) as caught:
        await world.pools[1].acquire_session(BrowserScope(owner, uuid4()))
    assert caught.value.reason is BrowserRefusalReason.CAPACITY
    world.pools[1]._browser.new_context.assert_not_awaited()


@pytest.mark.parametrize("whole_account", [False, True])
async def test_retirement_erases_only_selected_browser_recovery_and_workers_retire_contexts(
    world: _World, monkeypatch: pytest.MonkeyPatch, whole_account: bool
) -> None:
    monkeypatch.setattr(settings, "browser_max_concurrent_sessions", 3)
    owner = uuid4()
    first_scope, second_scope = BrowserScope(owner, uuid4()), BrowserScope(owner, uuid4())
    foreign_scope = browser_scope()
    first, second, foreign = world.pools
    first_session = await first.acquire_session(first_scope)
    second_session = await second.acquire_session(second_scope)
    foreign_session = await foreign.acquire_session(foreign_scope)
    monkeypatch.setattr(module, "_browser_pool", first)

    await module.forget_browser_sessions(owner, None if whole_account else first_scope.runtime_id)
    await second.cleanup_expired()
    await foreign.cleanup_expired()

    assert not first._sessions
    first_session.context.close.assert_awaited_once()
    if whole_account:
        assert not second._sessions
        second_session.context.close.assert_awaited_once()
    else:
        assert await second.acquire_session(second_scope) is second_session
        second_session.context.close.assert_not_awaited()
    assert await foreign.acquire_session(foreign_scope) is foreign_session
    foreign_session.context.close.assert_not_awaited()
    assert await coordination.renew(first_scope, uuid4().hex) is False


@pytest.mark.parametrize("unchanged_main", [False, True])
async def test_legacy_recovery_is_inherited_only_by_unchanged_historical_main(
    world: _World, monkeypatch: pytest.MonkeyPatch, unchanged_main: bool
) -> None:
    monkeypatch.setattr(settings, "browser_max_concurrent_sessions", 2)
    owner = uuid4()
    scope = BrowserScope(owner, owner if unchanged_main else uuid4())
    info = BrowserSessionInfo(
        session_id=uuid4().hex,
        user_id=str(owner),
        created_at=datetime.now(UTC),
        current_url="https://legacy.example/page",
        page_title="Legacy",
        worker_pid=123,
    )
    client = world.namespace.client
    key = world.namespace.prefix + REDIS_KEY_BROWSER_POOL_REGISTRY
    seconds, microseconds = await client.time()
    await client.hset(
        key,
        str(owner),
        json.dumps(
            {
                "expires_ms": seconds * 1000 + microseconds // 1000 + 60_000,
                "info": info.model_dump(mode="json"),
            }
        ),
    )

    session = await world.pools[0].acquire_session(scope)

    assert session.navigations == (["https://legacy.example/page"] if unchanged_main else [])
    assert bool(await client.hexists(key, str(owner))) is not unchanged_main
    assert await client.hexists(key, scope.key)


@pytest.mark.parametrize("wrong", ["owner", "runtime"])
async def test_recovery_writer_cannot_misattribute_metadata(world: _World, wrong: str) -> None:
    scope = browser_scope()
    info = BrowserSessionInfo(
        session_id=uuid4().hex,
        user_id=str(uuid4() if wrong == "owner" else scope.owner_id),
        runtime_id=uuid4() if wrong == "runtime" else scope.runtime_id,
        created_at=datetime.now(UTC),
        worker_pid=123,
    )
    with pytest.raises(BrowserRefusal):
        await coordination.reserve(scope, info)
    assert (
        await world.namespace.client.hlen(world.namespace.prefix + REDIS_KEY_BROWSER_POOL_REGISTRY)
        == 0
    )


async def test_account_retirement_attempts_every_context_even_after_one_closer_fails(
    world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "browser_max_concurrent_sessions", 2)
    pool = world.pools[0]
    monkeypatch.setattr(module, "_browser_pool", pool)
    first_context = AsyncMock(close=AsyncMock(side_effect=OSError("closed pipe")))
    second_context = AsyncMock()
    pool._browser.new_context.side_effect = [first_context, second_context]
    owner = uuid4()
    await pool.acquire_session(BrowserScope(owner, uuid4()))
    await pool.acquire_session(BrowserScope(owner, uuid4()))

    with pytest.raises(OSError):
        await module.forget_browser_sessions(owner)

    second_context.close.assert_awaited_once()
    assert not pool._sessions
    assert (
        await world.namespace.client.hlen(world.namespace.prefix + REDIS_KEY_BROWSER_POOL_REGISTRY)
        == 0
    )
