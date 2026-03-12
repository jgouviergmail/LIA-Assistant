"""Tests for UserMCPClientPool — tool metadata cache with ephemeral connections."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.infrastructure.mcp.user_pool import PoolEntry, UserMCPClientPool


@pytest.fixture
def pool():
    """Create a fresh pool instance for each test."""
    return UserMCPClientPool()


def _make_entry(user_id=None, server_id=None, last_used=None, active_calls=0):
    """Create a mock PoolEntry (metadata only, no session)."""
    return PoolEntry(
        user_id=user_id or uuid4(),
        server_id=server_id or uuid4(),
        last_used=last_used or time.monotonic(),
        url="https://mcp.example.com/sse",
        auth=MagicMock(),
        tools=[{"name": "test_tool", "description": "Test", "input_schema": {}}],
        active_calls=active_calls,
    )


class TestPoolSize:
    """Tests for pool size tracking."""

    def test_empty_pool(self, pool) -> None:
        """Should start with size 0."""
        assert pool.size == 0

    def test_size_after_adding_entries(self, pool) -> None:
        """Should track number of entries."""
        uid = uuid4()
        sid = uuid4()
        pool._entries[(uid, sid)] = _make_entry(uid, sid)
        assert pool.size == 1


class TestDisconnect:
    """Tests for disconnecting entries."""

    @pytest.mark.asyncio
    async def test_disconnect_removes_entry(self, pool) -> None:
        """Should remove entry from pool."""
        uid, sid = uuid4(), uuid4()
        pool._entries[(uid, sid)] = _make_entry(uid, sid)

        await pool.disconnect(uid, sid)
        assert pool.size == 0

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_is_noop(self, pool) -> None:
        """Should not raise when disconnecting non-existent entry."""
        await pool.disconnect(uuid4(), uuid4())  # Should not raise

    @pytest.mark.asyncio
    async def test_disconnect_user_removes_all(self, pool) -> None:
        """Should disconnect all servers for a specific user."""
        uid = uuid4()
        for _ in range(3):
            sid = uuid4()
            pool._entries[(uid, sid)] = _make_entry(uid, sid)

        other_uid = uuid4()
        other_sid = uuid4()
        pool._entries[(other_uid, other_sid)] = _make_entry(other_uid, other_sid)

        assert pool.size == 4
        await pool.disconnect_user(uid)
        assert pool.size == 1  # Only other user's entry remains

    @pytest.mark.asyncio
    async def test_disconnect_cleans_per_key_resources(self, pool) -> None:
        """Should clean up locks and timestamps to prevent memory leaks."""
        uid, sid = uuid4(), uuid4()
        key = (uid, sid)
        pool._entries[key] = _make_entry(uid, sid)

        # Simulate rate limit usage (creates per-key state)
        pool._call_timestamps[key].append(time.monotonic())

        await pool.disconnect(uid, sid)
        assert key not in pool._call_timestamps


class TestEvictIdle:
    """Tests for idle entry eviction."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.mcp.user_pool.settings")
    async def test_evict_old_entries(self, mock_settings, pool) -> None:
        """Should evict entries older than TTL."""
        mock_settings.mcp_user_pool_ttl_seconds = 10

        uid, sid = uuid4(), uuid4()
        pool._entries[(uid, sid)] = _make_entry(uid, sid, last_used=time.monotonic() - 20)

        evicted = await pool.evict_idle()
        assert evicted == 1
        assert pool.size == 0

    @pytest.mark.asyncio
    @patch("src.infrastructure.mcp.user_pool.settings")
    async def test_no_evict_active_calls(self, mock_settings, pool) -> None:
        """Should NOT evict entries with active tool calls."""
        mock_settings.mcp_user_pool_ttl_seconds = 10

        uid, sid = uuid4(), uuid4()
        pool._entries[(uid, sid)] = _make_entry(
            uid, sid, last_used=time.monotonic() - 20, active_calls=1
        )

        evicted = await pool.evict_idle()
        assert evicted == 0
        assert pool.size == 1

    @pytest.mark.asyncio
    @patch("src.infrastructure.mcp.user_pool.settings")
    async def test_no_evict_recent_entries(self, mock_settings, pool) -> None:
        """Should not evict recently used entries."""
        mock_settings.mcp_user_pool_ttl_seconds = 900

        uid, sid = uuid4(), uuid4()
        pool._entries[(uid, sid)] = _make_entry(uid, sid, last_used=time.monotonic())

        evicted = await pool.evict_idle()
        assert evicted == 0
        assert pool.size == 1


class TestShutdown:
    """Tests for pool shutdown."""

    @pytest.mark.asyncio
    async def test_shutdown_clears_all(self, pool) -> None:
        """Should remove all entries and clear internal state."""
        for _ in range(3):
            uid, sid = uuid4(), uuid4()
            pool._entries[(uid, sid)] = _make_entry(uid, sid)

        await pool.shutdown()
        assert pool.size == 0


class TestRateLimiting:
    """Tests for per-server rate limiting."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.mcp.user_pool.settings")
    async def test_rate_limit_exceeded(self, mock_settings, pool) -> None:
        """Should raise RuntimeError when rate limit is exceeded."""
        mock_settings.mcp_rate_limit_calls = 2
        mock_settings.mcp_rate_limit_window = 60

        key = (uuid4(), uuid4())

        # Exhaust the rate limit
        await pool._check_rate_limit(key)
        await pool._check_rate_limit(key)

        # Third call should fail
        with pytest.raises(RuntimeError, match="rate limit exceeded"):
            await pool._check_rate_limit(key)

    @pytest.mark.asyncio
    @patch("src.infrastructure.mcp.user_pool.settings")
    async def test_rate_limit_window_expiry(self, mock_settings, pool) -> None:
        """Should allow calls after the window expires."""
        mock_settings.mcp_rate_limit_calls = 1
        mock_settings.mcp_rate_limit_window = 0.01  # 10ms window

        key = (uuid4(), uuid4())

        await pool._check_rate_limit(key)

        # Wait for window to expire
        await asyncio.sleep(0.02)

        # Should succeed after window expiry
        await pool._check_rate_limit(key)


class TestCallTool:
    """Tests for tool execution via ephemeral connections."""

    @pytest.mark.asyncio
    async def test_call_missing_entry(self, pool) -> None:
        """Should raise RuntimeError when no pool entry exists."""
        with pytest.raises(RuntimeError, match="No pool entry"):
            await pool.call_tool(uuid4(), uuid4(), "test", {})

    @pytest.mark.asyncio
    @patch("src.infrastructure.mcp.user_pool.settings")
    async def test_call_increments_active_calls(self, mock_settings, pool) -> None:
        """Should increment and decrement active_calls counter."""
        mock_settings.mcp_rate_limit_calls = 100
        mock_settings.mcp_rate_limit_window = 60

        uid, sid = uuid4(), uuid4()
        entry = _make_entry(uid, sid)
        pool._entries[(uid, sid)] = entry

        assert entry.active_calls == 0

        with patch.object(
            pool,
            "_execute_call_ephemeral",
            new_callable=AsyncMock,
            return_value="result",
        ):
            result = await pool.call_tool(uid, sid, "test_tool", {})
            assert result == "result"

        assert entry.active_calls == 0  # Decremented in finally

    @pytest.mark.asyncio
    @patch("src.infrastructure.mcp.user_pool.settings")
    async def test_call_updates_last_used(self, mock_settings, pool) -> None:
        """Should update last_used timestamp on successful call."""
        mock_settings.mcp_rate_limit_calls = 100
        mock_settings.mcp_rate_limit_window = 60

        uid, sid = uuid4(), uuid4()
        entry = _make_entry(uid, sid, last_used=time.monotonic() - 100)
        pool._entries[(uid, sid)] = entry
        old_last_used = entry.last_used

        with patch.object(
            pool,
            "_execute_call_ephemeral",
            new_callable=AsyncMock,
            return_value="result",
        ):
            await pool.call_tool(uid, sid, "test_tool", {})

        assert entry.last_used > old_last_used

    @pytest.mark.asyncio
    @patch("src.infrastructure.mcp.user_pool.settings")
    async def test_call_passes_url_and_auth(self, mock_settings, pool) -> None:
        """Should pass entry's url and auth to ephemeral connection."""
        mock_settings.mcp_rate_limit_calls = 100
        mock_settings.mcp_rate_limit_window = 60

        uid, sid = uuid4(), uuid4()
        entry = _make_entry(uid, sid)
        entry.url = "https://mcp.example.com/sse"
        mock_auth = MagicMock()
        entry.auth = mock_auth
        pool._entries[(uid, sid)] = entry

        with patch.object(
            pool,
            "_execute_call_ephemeral",
            new_callable=AsyncMock,
            return_value="result",
        ) as mock_call:
            await pool.call_tool(uid, sid, "test_tool", {"query": "hello"})

            mock_call.assert_called_once_with(
                url="https://mcp.example.com/sse",
                auth=mock_auth,
                tool_name="test_tool",
                arguments={"query": "hello"},
                timeout_seconds=30,
            )

    @pytest.mark.asyncio
    @patch("src.infrastructure.mcp.user_pool.settings")
    async def test_call_decrements_on_error(self, mock_settings, pool) -> None:
        """Should decrement active_calls even when call fails."""
        mock_settings.mcp_rate_limit_calls = 100
        mock_settings.mcp_rate_limit_window = 60

        uid, sid = uuid4(), uuid4()
        entry = _make_entry(uid, sid)
        pool._entries[(uid, sid)] = entry

        with (
            patch.object(
                pool,
                "_execute_call_ephemeral",
                new_callable=AsyncMock,
                side_effect=RuntimeError("connection failed"),
            ),
            pytest.raises(RuntimeError, match="connection failed"),
        ):
            await pool.call_tool(uid, sid, "test_tool", {})

        assert entry.active_calls == 0


class TestGetOrConnect:
    """Tests for tool discovery via get_or_connect."""

    @pytest.mark.asyncio
    async def test_returns_cached_entry(self, pool) -> None:
        """Should return cached entry if one exists."""
        uid, sid = uuid4(), uuid4()
        existing = _make_entry(uid, sid)
        pool._entries[(uid, sid)] = existing

        result = await pool.get_or_connect(uid, sid, "url", MagicMock(), 30)
        assert result is existing

    @pytest.mark.asyncio
    async def test_updates_auth_on_reuse(self, pool) -> None:
        """Should update auth on cached entry (tokens may have been refreshed)."""
        uid, sid = uuid4(), uuid4()
        old_auth = MagicMock()
        existing = _make_entry(uid, sid)
        existing.auth = old_auth
        pool._entries[(uid, sid)] = existing

        new_auth = MagicMock()
        result = await pool.get_or_connect(uid, sid, "url", new_auth, 30)
        assert result.auth is new_auth

    @pytest.mark.asyncio
    async def test_discovers_tools_for_new_entry(self, pool) -> None:
        """Should call _discover_tools for new server and cache result."""
        uid, sid = uuid4(), uuid4()
        mock_tools = [{"name": "tool1", "description": "Tool 1", "input_schema": {}}]

        with patch.object(
            pool,
            "_discover_tools",
            new_callable=AsyncMock,
            return_value=(mock_tools, None),
        ):
            entry = await pool.get_or_connect(uid, sid, "https://mcp.example.com", MagicMock(), 30)

        assert entry.tools == mock_tools
        assert entry.reference_content is None
        assert pool.size == 1
