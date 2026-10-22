"""Atomic HTTP scan bans shared by workers, exercised against isolated real Redis."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from ipaddress import IPv6Address
from typing import Literal
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from src.core.config import settings
from src.infrastructure.rate_limiting import http_scan as module
from tests.redis_test_url import validated_test_redis_url

pytestmark = pytest.mark.integration


@dataclass
class _World:
    redis: Redis
    guards: tuple[module.RedisHTTPScanGuard, module.RedisHTTPScanGuard]
    ips: tuple[str, str]

    async def keys(self, client_ip: str) -> list[str]:
        return [key async for key in self.redis.scan_iter(match=f"http:scan:*{client_ip}*")]

    async def ban_key(self, client_ip: str) -> str:
        keys = [key for key in await self.keys(client_ip) if key.endswith(":ban")]
        assert len(keys) == 1
        return keys[0]


@pytest.fixture
async def world(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_World]:
    url = validated_test_redis_url(str(settings.redis_url))
    assert url is not None
    redis = Redis.from_url(url, decode_responses=True)
    # Unavailable promised infrastructure is a failure, never a green skip.
    await redis.ping()

    async def cache() -> Redis:
        return redis

    monkeypatch.setattr(module, "get_redis_cache", cache)
    monkeypatch.setattr(settings, "http_scan_protection_enabled", True)
    monkeypatch.setattr(settings, "http_scan_window_seconds", 60)
    monkeypatch.setattr(settings, "http_scan_not_found_limit", 20)
    monkeypatch.setattr(settings, "http_scan_auth_window_seconds", 600)
    monkeypatch.setattr(settings, "http_scan_auth_failure_limit", 20)
    monkeypatch.setattr(settings, "http_scan_ban_seconds", 900)
    # Exercise the real local service without making timing depend on a busy runner.
    monkeypatch.setattr(settings, "http_scan_redis_timeout_seconds", 2.0)
    prefix = int(IPv6Address("2001:db8::"))
    ips = tuple(str(IPv6Address(prefix | (uuid4().int & ((1 << 64) - 1)))) for _ in range(2))
    world = _World(
        redis, (module.RedisHTTPScanGuard(), module.RedisHTTPScanGuard()), (ips[0], ips[1])
    )
    try:
        yield world
    finally:
        keys = [key for ip in world.ips for key in await world.keys(ip)]
        if keys:
            await redis.delete(*keys)
        await redis.aclose()


@pytest.mark.parametrize("reason", ["not_found", "credentials"])
async def test_concurrent_workers_create_exactly_one_ban(
    world: _World, reason: Literal["not_found", "credentials"]
) -> None:
    ip = world.ips[0]
    limit = (
        settings.http_scan_not_found_limit
        if reason == "not_found"
        else settings.http_scan_auth_failure_limit
    )

    outcomes = await asyncio.gather(
        *(world.guards[index % 2].record(ip, reason, uuid4().hex) for index in range(limit * 2))
    )

    assert sum(outcomes) == 1
    assert all(await asyncio.gather(*(guard.remaining(ip) for guard in world.guards)))
    assert 0 < await world.redis.ttl(await world.ban_key(ip)) <= settings.http_scan_ban_seconds


async def test_repeated_missing_path_is_one_strike_across_workers(world: _World) -> None:
    first, second = world.guards
    ip = world.ips[0]

    duplicates = await asyncio.gather(
        *(world.guards[index % 2].record(ip, "not_found", "same-path") for index in range(80))
    )

    assert not any(duplicates)
    assert await first.remaining(ip) == 0
    for index in range(settings.http_scan_not_found_limit - 2):
        assert not await first.record(ip, "not_found", f"other-path-{index}")
    assert not await second.remaining(ip)
    assert await second.record(ip, "not_found", "last-distinct-path")


async def test_distinct_credential_attempts_reach_their_own_threshold(world: _World) -> None:
    guard = world.guards[0]
    ip = world.ips[0]

    for _ in range(settings.http_scan_auth_failure_limit - 1):
        assert not await guard.record(ip, "credentials", uuid4().hex)
    assert await guard.remaining(ip) == 0

    assert await world.guards[1].record(ip, "credentials", uuid4().hex)


async def test_failure_reasons_do_not_share_a_counter(world: _World) -> None:
    guard = world.guards[0]
    ip = world.ips[0]

    for index in range(settings.http_scan_not_found_limit - 1):
        assert not await guard.record(ip, "not_found", f"path-{index}")
    for _ in range(settings.http_scan_auth_failure_limit - 1):
        assert not await guard.record(ip, "credentials", uuid4().hex)

    assert await guard.remaining(ip) == 0
    assert await world.guards[1].record(ip, "credentials", uuid4().hex)


async def test_banning_one_address_preserves_another_addresses_budget(world: _World) -> None:
    guard = world.guards[0]
    first_ip, second_ip = world.ips

    for index in range(settings.http_scan_not_found_limit):
        await guard.record(first_ip, "not_found", f"first-{index}")

    assert await world.guards[1].remaining(first_ip) > 0
    assert await world.guards[1].remaining(second_ip) == 0
    assert not await world.guards[1].record(second_ip, "not_found", "first-second-ip-path")
    assert await guard.remaining(second_ip) == 0


async def test_rejected_requests_never_renew_the_existing_ban(world: _World) -> None:
    ip = world.ips[0]
    first, second = world.guards
    for index in range(settings.http_scan_not_found_limit):
        await first.record(ip, "not_found", f"path-{index}")
    ban_key = await world.ban_key(ip)
    assert await world.redis.pexpire(ban_key, 2_000)
    before = await world.redis.pttl(ban_key)

    outcomes = await asyncio.gather(
        *(
            world.guards[index % 2].record(
                ip, "not_found" if index % 2 else "credentials", uuid4().hex
            )
            for index in range(40)
        )
    )

    assert not any(outcomes)
    assert 0 < await world.redis.pttl(ban_key) <= before
    assert 0 < await second.remaining(ip) <= 2


async def test_expired_scan_state_restores_a_fresh_budget(world: _World) -> None:
    first, second = world.guards
    ip = world.ips[0]
    for index in range(settings.http_scan_not_found_limit):
        await first.record(ip, "not_found", f"path-{index}")
    keys = await world.keys(ip)
    assert keys
    for key in keys:
        assert await world.redis.pexpire(key, 1)
    await asyncio.sleep(0.03)

    assert await second.remaining(ip) == 0
    assert not await second.record(ip, "not_found", "new-path-after-expiry")
    assert await first.remaining(ip) == 0


async def test_stale_distinct_paths_slide_out_of_the_window(world: _World) -> None:
    guard = world.guards[0]
    ip = world.ips[0]
    for index in range(settings.http_scan_not_found_limit - 1):
        assert not await guard.record(ip, "not_found", f"old-path-{index}")
    counters = [key for key in await world.keys(ip) if await world.redis.type(key) == "zset"]
    assert len(counters) == 1
    # Redis time still drives the Lua decision; only this test's observations are aged.
    members = await world.redis.zrange(counters[0], 0, -1)
    await world.redis.zadd(counters[0], dict.fromkeys(members, 0))

    assert not await world.guards[1].record(ip, "not_found", "current-path")
    assert await guard.remaining(ip) == 0
    assert await world.redis.zcard(counters[0]) == 1
    assert await world.redis.ttl(counters[0]) > 0


async def test_all_owned_keys_expire(world: _World) -> None:
    ip = world.ips[0]
    await world.guards[0].record(ip, "not_found", "missing-path")
    await world.guards[1].record(ip, "credentials", uuid4().hex)
    keys = await world.keys(ip)

    assert keys
    assert all(ttl > 0 for ttl in await asyncio.gather(*(world.redis.ttl(key) for key in keys)))
