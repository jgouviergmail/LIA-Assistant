"""Quota refusals keep their deadline and stop calls before transport I/O."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx2
import pytest
from mcp import types
from mcp.client import Client
from redis.asyncio import Redis
from redis.exceptions import ConnectionError

from src.infrastructure.mcp.rate_limit import (
    MCPRateLimitError,
    MCPServerCooldown,
    MCPToolExecutionError,
    quota_error,
)
from src.infrastructure.mcp.user_pool import PoolEntry, UserMCPClientPool, _surface_root_cause


@pytest.mark.parametrize(
    "message, delay",
    [
        ("Rate limit exceeded. Please retry after 23s, resets later", 23),
        ("Too many requests; retry in 1.5 seconds", 2),
        ("Rate limit exceeded", 60),
        ("Rate limit exceeded; retry after 0s", 60),
    ],
)
def test_tool_quota_delay(message: str, delay: int) -> None:
    error = quota_error(MCPToolExecutionError(message), 60)
    assert error is not None
    assert error.retry_after == delay
    assert "Do not call this server's other methods" in str(error)


def test_non_quota_tool_failure_and_unrelated_runtime_are_not_reclassified() -> None:
    assert quota_error(MCPToolExecutionError("Resource not found"), 60) is None
    assert quota_error(RuntimeError("Rate limit exceeded"), 60) is None


@pytest.mark.parametrize("header, expected", [("12", 12), ("garbage", 60), ("NaN", 60)])
def test_http_429_retry_after(header: str, expected: int) -> None:
    request = httpx2.Request("POST", "https://example.test/mcp")
    response = httpx2.Response(429, headers={"Retry-After": header}, request=request)
    error = quota_error(httpx2.HTTPStatusError("quota", request=request, response=response), 60)
    assert error is not None
    assert error.retry_after == expected


def test_nested_quota_is_not_logged_as_a_transport_crash() -> None:
    error = ExceptionGroup(
        "transport",
        [
            ExceptionGroup(
                "session", [MCPToolExecutionError("Rate limit exceeded; retry after 23s")]
            )
        ],
    )
    with patch("src.infrastructure.mcp.user_pool.logger") as logger:
        with pytest.raises(MCPRateLimitError) as raised:
            _surface_root_cause(error, log_event="mcp_ephemeral_call_failed")
    assert raised.value.retry_after == 23
    logger.error.assert_not_called()
    logger.warning.assert_not_called()


async def test_ephemeral_tool_quota_is_typed_and_closes_connection() -> None:
    client = MagicMock(spec=Client)
    client.call_tool = AsyncMock(
        return_value=types.CallToolResult(
            is_error=True,
            content=[types.TextContent(text="Rate limit exceeded; retry after 23s")],
        )
    )
    connection = MagicMock()
    connection.__aenter__.return_value = client
    with (
        patch("src.infrastructure.mcp.user_pool._ephemeral_client", return_value=connection),
        patch("src.infrastructure.mcp.user_pool.logger") as logger,
    ):
        with pytest.raises(MCPRateLimitError) as raised:
            await UserMCPClientPool._execute_call_ephemeral(
                "https://example.test/mcp", None, "scrape", {"url": "https://source.test"}, 5
            )
    assert raised.value.retry_after == 23
    client.call_tool.assert_awaited_once_with("scrape", {"url": "https://source.test"})
    connection.__aexit__.assert_awaited_once()
    logger.error.assert_not_called()


async def test_http_discovery_quota_stops_reconnect_before_transport() -> None:
    request = httpx2.Request("POST", "https://example.test/mcp")
    response = httpx2.Response(429, headers={"Retry-After": "12"}, request=request)
    client = MagicMock(spec=Client)
    client.list_tools = AsyncMock(
        side_effect=ExceptionGroup(
            "session", [httpx2.HTTPStatusError("quota", request=request, response=response)]
        )
    )
    connection = MagicMock()
    connection.__aenter__.return_value = client
    cooldown = MagicMock(spec=MCPServerCooldown)
    cooldown.remaining = AsyncMock(side_effect=[0.0, 11.0])
    cooldown.record = AsyncMock()
    pool = UserMCPClientPool(cooldowns=cooldown)
    key = (uuid4(), uuid4())
    with patch(
        "src.infrastructure.mcp.user_pool._ephemeral_client", return_value=connection
    ) as connect:
        with pytest.raises(MCPRateLimitError):
            await pool.get_or_connect(*key, "https://example.test/mcp", None, 5)
        with pytest.raises(MCPRateLimitError) as blocked:
            await pool.get_or_connect(*key, "https://example.test/mcp", None, 5)
    assert blocked.value.retry_after == 11
    cooldown.record.assert_awaited_once_with(key, 12)
    assert pool.size == 0
    connect.assert_called_once()
    connection.__aexit__.assert_awaited_once()


async def test_pool_blocks_all_methods_during_server_cooldown() -> None:
    cooldown = MagicMock(spec=MCPServerCooldown)
    cooldown.remaining = AsyncMock(side_effect=[0.0, 22.0])
    cooldown.record = AsyncMock()
    pool = UserMCPClientPool(cooldowns=cooldown)
    key = (uuid4(), uuid4())
    pool._entries[key] = PoolEntry(user_id=key[0], server_id=key[1], last_used=0)
    with patch.object(pool, "_execute_call_ephemeral", new_callable=AsyncMock) as execute:
        execute.side_effect = MCPRateLimitError(23)
        with pytest.raises(MCPRateLimitError):
            await pool.call_tool(*key, "scrape", {})
        with pytest.raises(MCPRateLimitError) as blocked:
            await pool.call_tool(*key, "search", {})
    assert blocked.value.retry_after == 22
    assert execute.await_count == 1
    cooldown.record.assert_awaited_once_with(key, 23)
    assert pool._entries[key].active_calls == 0


async def test_pool_resumes_after_cooldown() -> None:
    cooldown = MagicMock(spec=MCPServerCooldown)
    cooldown.remaining = AsyncMock(return_value=0.0)
    pool = UserMCPClientPool(cooldowns=cooldown)
    key = (uuid4(), uuid4())
    pool._entries[key] = PoolEntry(user_id=key[0], server_id=key[1], last_used=0)
    with patch.object(pool, "_execute_call_ephemeral", new_callable=AsyncMock) as execute:
        execute.return_value = "result"
        assert await pool.call_tool(*key, "search", {}) == "result"
    execute.assert_awaited_once()


async def test_resource_read_during_cooldown_uses_fallback_without_transport_or_extension() -> None:
    cooldown = MagicMock(spec=MCPServerCooldown)
    cooldown.remaining = AsyncMock(return_value=23)
    cooldown.record = AsyncMock()
    pool = UserMCPClientPool(cooldowns=cooldown)
    key = (uuid4(), uuid4())
    pool._entries[key] = PoolEntry(user_id=key[0], server_id=key[1], last_used=0)
    with (
        patch.object(pool, "_execute_read_resource_ephemeral", new_callable=AsyncMock) as read,
        patch("src.infrastructure.mcp.user_pool.logger") as logger,
    ):
        assert await pool.read_resource(*key, "ui://example/view") is None
    read.assert_not_awaited()
    cooldown.record.assert_not_awaited()
    logger.info.assert_called_once()
    logger.warning.assert_not_called()


async def test_resource_http_quota_records_deadline_without_warning_and_closes_connection() -> None:
    request = httpx2.Request("POST", "https://example.test/mcp")
    response = httpx2.Response(429, headers={"Retry-After": "12"}, request=request)
    client = MagicMock(spec=Client)
    client.read_resource = AsyncMock(
        side_effect=ExceptionGroup(
            "session", [httpx2.HTTPStatusError("quota", request=request, response=response)]
        )
    )
    connection = MagicMock()
    connection.__aenter__.return_value = client
    cooldown = MagicMock(spec=MCPServerCooldown)
    cooldown.remaining = AsyncMock(return_value=0)
    cooldown.record = AsyncMock()
    pool = UserMCPClientPool(cooldowns=cooldown)
    key = (uuid4(), uuid4())
    pool._entries[key] = PoolEntry(user_id=key[0], server_id=key[1], last_used=0)
    with (
        patch("src.infrastructure.mcp.user_pool._ephemeral_client", return_value=connection),
        patch("src.infrastructure.mcp.user_pool.logger") as logger,
    ):
        assert await pool.read_resource(*key, "ui://example/view") is None
    cooldown.record.assert_awaited_once_with(key, 12)
    client.read_resource.assert_awaited_once_with("ui://example/view")
    connection.__aexit__.assert_awaited_once()
    logger.info.assert_called_once()
    logger.warning.assert_not_called()
    logger.error.assert_not_called()


async def test_redis_outage_keeps_known_deadline() -> None:
    redis = AsyncMock(spec=Redis)
    redis.eval = AsyncMock(side_effect=ConnectionError("unavailable"))
    redis.pttl = AsyncMock(side_effect=ConnectionError("unavailable"))
    cooldown = MCPServerCooldown()
    key = (uuid4(), uuid4())
    with patch("src.infrastructure.mcp.rate_limit.get_redis_cache", AsyncMock(return_value=redis)):
        await cooldown.record(key, 23)
        assert 22 < await cooldown.remaining(key) <= 23


async def test_shared_deadline_remains_known_when_redis_goes_down() -> None:
    redis = AsyncMock(spec=Redis)
    redis.pttl = AsyncMock(side_effect=[23000, ConnectionError("unavailable")])
    cooldown = MCPServerCooldown()
    key = (uuid4(), uuid4())
    with patch("src.infrastructure.mcp.rate_limit.get_redis_cache", AsyncMock(return_value=redis)):
        assert await cooldown.remaining(key) == 23
        assert 22 < await cooldown.remaining(key) <= 23


async def test_record_adopts_longer_shared_deadline_before_outage_and_reconnect() -> None:
    redis = AsyncMock(spec=Redis)
    redis.eval = AsyncMock(return_value=23000)
    redis.pttl = AsyncMock(side_effect=ConnectionError("unavailable"))
    cooldown = MCPServerCooldown()
    key = (uuid4(), uuid4())
    with patch("src.infrastructure.mcp.rate_limit.get_redis_cache", AsyncMock(return_value=redis)):
        await cooldown.record(key, 2)
        cooldown.forget_local(key)
        assert 22 < await cooldown.remaining(key) <= 23


@pytest.mark.parametrize("read_fails", [False, True])
async def test_pending_redis_read_cannot_erase_a_newer_local_refusal(read_fails: bool) -> None:
    started, release = asyncio.Event(), asyncio.Event()
    redis = AsyncMock(spec=Redis)

    async def old_read(_key: str) -> int:
        started.set()
        await release.wait()
        if read_fails:
            raise ConnectionError("read unavailable")
        return 1000

    redis.pttl.side_effect = old_read
    redis.eval.side_effect = ConnectionError("write unavailable")
    cooldown = MCPServerCooldown()
    key = (uuid4(), uuid4())
    with (
        patch("src.infrastructure.mcp.rate_limit.time.monotonic", return_value=100),
        patch("src.infrastructure.mcp.rate_limit.get_redis_cache", AsyncMock(return_value=redis)),
    ):
        cooldown._deadlines[key] = 105
        reading = asyncio.create_task(cooldown.remaining(key))
        await started.wait()
        await cooldown.record(key, 600)
        release.set()
        assert await reading == 600
        assert cooldown._deadlines[key] == 700


async def test_pending_redis_record_can_merge_after_expired_local_state_is_pruned() -> None:
    started, release = asyncio.Event(), asyncio.Event()
    redis = AsyncMock(spec=Redis)

    async def shared_record(*_args: object) -> int:
        started.set()
        await release.wait()
        return 23000

    redis.eval.side_effect = shared_record
    redis.pttl.side_effect = ConnectionError("read unavailable")
    cooldown = MCPServerCooldown()
    key = (uuid4(), uuid4())
    with (
        patch("src.infrastructure.mcp.rate_limit.time.monotonic", return_value=100) as clock,
        patch("src.infrastructure.mcp.rate_limit.get_redis_cache", AsyncMock(return_value=redis)),
    ):
        recording = asyncio.create_task(cooldown.record(key, 1))
        await started.wait()
        clock.return_value = 102
        cooldown.forget_local(key)
        assert key not in cooldown._deadlines
        release.set()
        await recording
        assert await cooldown.remaining(key) == 23
