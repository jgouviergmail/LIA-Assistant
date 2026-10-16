"""A server that failed to connect is not retried at every turn (point 29).

Measured: a dead personal MCP server set no pause at all. Every turn opened a
new connection to it, one server after another, each attempt up to its
timeout — the person waited for servers known to be down. A connection failure
now pauses the server in Redis (shared by every worker), the pause doubling up
to its cap; the manual test bypasses it, and a success clears it. A quota
refusal keeps its own, provider-declared cooldown.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.infrastructure.mcp.rate_limit import (
    MCPRateLimitError,
    MCPServerCooldown,
    MCPServerFailures,
    MCPServerPausedError,
)
from src.infrastructure.mcp.user_pool import UserMCPClientPool

pytestmark = pytest.mark.unit

_URL = "https://mcp.example.test/mcp"


def _pool(*, paused_for: float = 0.0) -> tuple[UserMCPClientPool, MagicMock]:
    cooldowns = MagicMock(spec=MCPServerCooldown)
    cooldowns.remaining = AsyncMock(return_value=0.0)
    cooldowns.record = AsyncMock()
    failures = MagicMock(spec=MCPServerFailures)
    failures.remaining = AsyncMock(return_value=paused_for)
    failures.record = AsyncMock(return_value=30.0)
    failures.clear = AsyncMock()
    return UserMCPClientPool(cooldowns=cooldowns, failures=failures), failures


class TestAFailedConnectionPausesTheServer:
    async def test_the_failure_is_recorded_and_still_raised(self) -> None:
        pool, failures = _pool()
        key = (uuid4(), uuid4())
        with patch.object(
            pool, "_discover_tools", new=AsyncMock(side_effect=ConnectionError("refused"))
        ):
            with pytest.raises(ConnectionError):
                await pool.get_or_connect(*key, _URL, None, 5)

        failures.record.assert_awaited_once_with(key)
        failures.clear.assert_not_awaited()

    async def test_a_paused_server_is_skipped_without_a_connection(self) -> None:
        pool, _ = _pool(paused_for=42.0)
        key = (uuid4(), uuid4())
        discover = AsyncMock()
        with patch.object(pool, "_discover_tools", new=discover):
            with pytest.raises(MCPServerPausedError) as paused:
                await pool.get_or_connect(*key, _URL, None, 5)

        discover.assert_not_awaited()
        assert paused.value.retry_in_seconds == 42

    async def test_a_success_clears_the_pause(self) -> None:
        pool, failures = _pool()
        key = (uuid4(), uuid4())
        with patch.object(pool, "_discover_tools", new=AsyncMock(return_value=([], None))):
            await pool.get_or_connect(*key, _URL, None, 5)

        failures.clear.assert_awaited_once_with(key)
        failures.record.assert_not_awaited()


class TestTheManualTestAndTheQuota:
    async def test_the_manual_test_reaches_a_paused_server(self) -> None:
        """The person pressing « test » after fixing the server must not wait."""
        pool, failures = _pool(paused_for=600.0)
        key = (uuid4(), uuid4())
        with patch.object(pool, "_discover_tools", new=AsyncMock(return_value=([], None))):
            await pool.get_or_connect(*key, _URL, None, 5, force_refresh=True)

        failures.remaining.assert_not_awaited()
        failures.clear.assert_awaited_once_with(key)

    async def test_a_server_whose_settings_change_is_tried_again_at_once(self) -> None:
        """Editing, toggling or re-authorising a server disconnects it: the new
        configuration deserves a fresh try, not the old one's pause."""
        pool, failures = _pool(paused_for=600.0)
        key = (uuid4(), uuid4())

        await pool.disconnect(*key)

        failures.clear.assert_awaited_once_with(key)

    async def test_a_quota_refusal_is_not_a_failure(self) -> None:
        """A provider-declared cooldown is the provider's; it never feeds the pause."""
        pool, failures = _pool()
        key = (uuid4(), uuid4())
        with patch.object(
            pool, "_discover_tools", new=AsyncMock(side_effect=MCPRateLimitError(12))
        ):
            with pytest.raises(MCPRateLimitError):
                await pool.get_or_connect(*key, _URL, None, 5)

        failures.record.assert_not_awaited()
