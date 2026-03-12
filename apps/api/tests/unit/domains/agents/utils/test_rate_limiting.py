"""
Unit tests for tool rate limiting utilities.

Tests for rate limiting tool invocations in LangGraph agents
with sliding window algorithm and per-user isolation.
"""

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.utils.rate_limiting import (
    _rate_limit_tracker,
    get_rate_limit_status,
    rate_limit,
    reset_rate_limits,
)

# Patch path for get_settings (imported inside wrapper)
SETTINGS_PATCH_PATH = "src.core.config.get_settings"


# ============================================================================
# Test fixtures and helpers
# ============================================================================


@pytest.fixture(autouse=True)
def reset_tracker():
    """Reset rate limit tracker before each test."""
    _rate_limit_tracker.clear()
    yield
    _rate_limit_tracker.clear()


@pytest.fixture
def mock_runtime():
    """Create a mock ToolRuntime with user_id."""
    runtime = MagicMock()
    runtime.config = {"configurable": {"user_id": "test_user_123"}}
    return runtime


@pytest.fixture
def mock_settings():
    """Create mock settings with rate limiting enabled."""
    settings = MagicMock()
    settings.rate_limit_enabled = True
    return settings


@pytest.fixture
def mock_settings_disabled():
    """Create mock settings with rate limiting disabled."""
    settings = MagicMock()
    settings.rate_limit_enabled = False
    return settings


# ============================================================================
# Tests for rate_limit decorator basic functionality
# ============================================================================


class TestRateLimitDecoratorBasic:
    """Tests for basic rate_limit decorator functionality."""

    @pytest.mark.asyncio
    async def test_allows_calls_under_limit(self, mock_runtime, mock_settings):
        """Test that calls under the limit are allowed."""

        @rate_limit(max_calls=5, window_seconds=60)
        async def test_tool(runtime=None):
            return "success"

        with patch(SETTINGS_PATCH_PATH, return_value=mock_settings):
            with patch("src.domains.agents.utils.rate_limiting.agent_tool_rate_limit_hits"):
                # Make 3 calls (under limit of 5)
                for _ in range(3):
                    result = await test_tool(runtime=mock_runtime)
                    assert result == "success"

    @pytest.mark.asyncio
    async def test_blocks_calls_over_limit(self, mock_runtime, mock_settings):
        """Test that calls over the limit are blocked."""

        @rate_limit(max_calls=3, window_seconds=60)
        async def test_tool(runtime=None):
            return "success"

        with patch(SETTINGS_PATCH_PATH, return_value=mock_settings):
            with patch("src.domains.agents.utils.rate_limiting.agent_tool_rate_limit_hits"):
                # Make 3 calls (at limit)
                for _ in range(3):
                    result = await test_tool(runtime=mock_runtime)
                    assert result == "success"

                # 4th call should be blocked
                result = await test_tool(runtime=mock_runtime)
                response = json.loads(result)
                assert response["error"] == "rate_limit_exceeded"

    @pytest.mark.asyncio
    async def test_returns_error_json_on_limit(self, mock_runtime, mock_settings):
        """Test that rate limit error returns proper JSON structure."""

        @rate_limit(max_calls=1, window_seconds=60)
        async def test_tool(runtime=None):
            return "success"

        with patch(SETTINGS_PATCH_PATH, return_value=mock_settings):
            with patch("src.domains.agents.utils.rate_limiting.agent_tool_rate_limit_hits"):
                # First call succeeds
                await test_tool(runtime=mock_runtime)

                # Second call blocked
                result = await test_tool(runtime=mock_runtime)
                response = json.loads(result)

                assert "error" in response
                assert "message" in response
                assert "retry_after_seconds" in response
                assert "limit" in response
                assert "tool_name" in response


class TestRateLimitDecoratorDisabled:
    """Tests for rate limiting when disabled."""

    @pytest.mark.asyncio
    async def test_allows_all_calls_when_disabled(self, mock_runtime, mock_settings_disabled):
        """Test that all calls are allowed when rate limiting is disabled."""

        @rate_limit(max_calls=2, window_seconds=60)
        async def test_tool(runtime=None):
            return "success"

        with patch(SETTINGS_PATCH_PATH, return_value=mock_settings_disabled):
            # Make 10 calls (would exceed limit if enabled)
            for _ in range(10):
                result = await test_tool(runtime=mock_runtime)
                assert result == "success"

    @pytest.mark.asyncio
    async def test_clears_tracker_when_disabled(self, mock_runtime, mock_settings_disabled):
        """Test that tracker is cleared when rate limiting is disabled."""
        # Pre-populate tracker
        _rate_limit_tracker[("test_tool", "user123")] = [time.time()]

        @rate_limit(max_calls=5, window_seconds=60)
        async def test_tool(runtime=None):
            return "success"

        with patch(SETTINGS_PATCH_PATH, return_value=mock_settings_disabled):
            await test_tool(runtime=mock_runtime)

            # Tracker should be cleared
            assert len(_rate_limit_tracker) == 0


class TestRateLimitDecoratorNoRuntime:
    """Tests for rate limiting without runtime."""

    @pytest.mark.asyncio
    async def test_allows_call_without_runtime(self, mock_settings):
        """Test that calls are allowed when runtime is missing (fail open)."""

        @rate_limit(max_calls=1, window_seconds=60)
        async def test_tool():
            return "success"

        with patch(SETTINGS_PATCH_PATH, return_value=mock_settings):
            with patch("src.domains.agents.utils.rate_limiting.logger") as mock_logger:
                # Call without runtime
                result = await test_tool()
                assert result == "success"
                mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_allows_call_without_user_id(self, mock_settings):
        """Test that calls are allowed when user_id is missing (fail open)."""
        runtime = MagicMock()
        runtime.config = {"configurable": {}}  # No user_id

        @rate_limit(max_calls=1, window_seconds=60)
        async def test_tool(runtime=None):
            return "success"

        with patch(SETTINGS_PATCH_PATH, return_value=mock_settings):
            with patch("src.domains.agents.utils.rate_limiting.logger") as mock_logger:
                result = await test_tool(runtime=runtime)
                assert result == "success"
                mock_logger.warning.assert_called()


class TestRateLimitDecoratorScopes:
    """Tests for different rate limit scopes."""

    @pytest.mark.asyncio
    async def test_user_scope_isolates_users(self, mock_settings):
        """Test that user scope isolates rate limits per user."""

        @rate_limit(max_calls=2, window_seconds=60, scope="user")
        async def test_tool(runtime=None):
            return "success"

        user1_runtime = MagicMock()
        user1_runtime.config = {"configurable": {"user_id": "user_1"}}

        user2_runtime = MagicMock()
        user2_runtime.config = {"configurable": {"user_id": "user_2"}}

        with patch(SETTINGS_PATCH_PATH, return_value=mock_settings):
            with patch("src.domains.agents.utils.rate_limiting.agent_tool_rate_limit_hits"):
                # User 1 makes 2 calls (at limit)
                for _ in range(2):
                    result = await test_tool(runtime=user1_runtime)
                    assert result == "success"

                # User 2 can still make calls (separate limit)
                result = await test_tool(runtime=user2_runtime)
                assert result == "success"

    @pytest.mark.asyncio
    async def test_global_scope_shares_limit(self, mock_settings):
        """Test that global scope shares rate limit across users."""

        @rate_limit(max_calls=2, window_seconds=60, scope="global")
        async def test_tool(runtime=None):
            return "success"

        user1_runtime = MagicMock()
        user1_runtime.config = {"configurable": {"user_id": "user_1"}}

        user2_runtime = MagicMock()
        user2_runtime.config = {"configurable": {"user_id": "user_2"}}

        with patch(SETTINGS_PATCH_PATH, return_value=mock_settings):
            with patch("src.domains.agents.utils.rate_limiting.agent_tool_rate_limit_hits"):
                # User 1 makes 2 calls (at global limit)
                for _ in range(2):
                    await test_tool(runtime=user1_runtime)

                # User 2's call is blocked (shared limit)
                result = await test_tool(runtime=user2_runtime)
                response = json.loads(result)
                assert response["error"] == "rate_limit_exceeded"


class TestRateLimitDecoratorSlidingWindow:
    """Tests for sliding window rate limiting."""

    @pytest.mark.asyncio
    async def test_sliding_window_expires_old_calls(self, mock_runtime, mock_settings):
        """Test that old calls expire from the window."""

        @rate_limit(max_calls=2, window_seconds=1)  # 1 second window
        async def test_tool(runtime=None):
            return "success"

        with patch(SETTINGS_PATCH_PATH, return_value=mock_settings):
            with patch("src.domains.agents.utils.rate_limiting.agent_tool_rate_limit_hits"):
                # Make 2 calls (at limit)
                for _ in range(2):
                    await test_tool(runtime=mock_runtime)

                # Wait for window to expire
                time.sleep(1.1)

                # Should be able to make new calls
                result = await test_tool(runtime=mock_runtime)
                assert result == "success"


class TestRateLimitDecoratorDynamicLimits:
    """Tests for dynamic (callable) rate limits."""

    @pytest.mark.asyncio
    async def test_callable_max_calls(self, mock_runtime, mock_settings):
        """Test that max_calls can be a callable."""
        call_count = [0]

        def dynamic_max_calls():
            call_count[0] += 1
            return 3

        @rate_limit(max_calls=dynamic_max_calls, window_seconds=60)
        async def test_tool(runtime=None):
            return "success"

        with patch(SETTINGS_PATCH_PATH, return_value=mock_settings):
            with patch("src.domains.agents.utils.rate_limiting.agent_tool_rate_limit_hits"):
                await test_tool(runtime=mock_runtime)

        # Callable should have been called
        assert call_count[0] > 0

    @pytest.mark.asyncio
    async def test_callable_window_seconds(self, mock_runtime, mock_settings):
        """Test that window_seconds can be a callable."""
        call_count = [0]

        def dynamic_window():
            call_count[0] += 1
            return 60

        @rate_limit(max_calls=5, window_seconds=dynamic_window)
        async def test_tool(runtime=None):
            return "success"

        with patch(SETTINGS_PATCH_PATH, return_value=mock_settings):
            with patch("src.domains.agents.utils.rate_limiting.agent_tool_rate_limit_hits"):
                await test_tool(runtime=mock_runtime)

        assert call_count[0] > 0


class TestRateLimitDecoratorMetrics:
    """Tests for metrics tracking."""

    @pytest.mark.asyncio
    async def test_increments_metric_on_limit_exceeded(self, mock_runtime, mock_settings):
        """Test that Prometheus metric is incremented when limit exceeded."""

        @rate_limit(max_calls=1, window_seconds=60)
        async def test_tool(runtime=None):
            return "success"

        with patch(SETTINGS_PATCH_PATH, return_value=mock_settings):
            with patch(
                "src.domains.agents.utils.rate_limiting.agent_tool_rate_limit_hits"
            ) as mock_metric:
                # First call succeeds
                await test_tool(runtime=mock_runtime)

                # Second call exceeds limit
                await test_tool(runtime=mock_runtime)

                # Metric should be incremented
                mock_metric.labels.assert_called()
                mock_metric.labels().inc.assert_called()


class TestRateLimitDecoratorCustomMessage:
    """Tests for custom error messages."""

    @pytest.mark.asyncio
    async def test_uses_custom_error_message(self, mock_runtime, mock_settings):
        """Test that custom error message is used."""
        custom_message = "Custom rate limit message"

        @rate_limit(max_calls=1, window_seconds=60, error_message=custom_message)
        async def test_tool(runtime=None):
            return "success"

        with patch(SETTINGS_PATCH_PATH, return_value=mock_settings):
            with patch("src.domains.agents.utils.rate_limiting.agent_tool_rate_limit_hits"):
                # First call succeeds
                await test_tool(runtime=mock_runtime)

                # Second call blocked
                result = await test_tool(runtime=mock_runtime)
                response = json.loads(result)

                assert response["message"] == custom_message


# ============================================================================
# Tests for get_rate_limit_status
# ============================================================================


class TestGetRateLimitStatus:
    """Tests for get_rate_limit_status function."""

    def test_returns_empty_for_no_history(self):
        """Test returns empty status when no call history."""
        status = get_rate_limit_status("unknown_tool", "unknown_user")

        assert status["calls_in_window"] == 0
        assert status["oldest_call_age_seconds"] == 0
        assert status["call_timestamps"] == []

    def test_returns_correct_call_count(self):
        """Test returns correct number of calls in window."""
        # Add some calls to tracker
        _rate_limit_tracker[("test_tool", "user123")] = [
            time.time() - 30,
            time.time() - 20,
            time.time() - 10,
        ]

        status = get_rate_limit_status("test_tool", "user123")

        assert status["calls_in_window"] == 3

    def test_returns_oldest_call_age(self):
        """Test returns correct age of oldest call."""
        now = time.time()
        _rate_limit_tracker[("test_tool", "user123")] = [
            now - 50,  # 50 seconds ago
            now - 30,
            now - 10,
        ]

        status = get_rate_limit_status("test_tool", "user123")

        # Should be approximately 50 seconds
        assert 49 <= status["oldest_call_age_seconds"] <= 51

    def test_returns_timestamps(self):
        """Test returns call timestamps."""
        timestamps = [time.time() - 30, time.time() - 20, time.time() - 10]
        _rate_limit_tracker[("test_tool", "user123")] = timestamps

        status = get_rate_limit_status("test_tool", "user123")

        assert status["call_timestamps"] == timestamps


# ============================================================================
# Tests for reset_rate_limits
# ============================================================================


class TestResetRateLimits:
    """Tests for reset_rate_limits function."""

    def test_reset_all(self):
        """Test resetting all rate limits."""
        _rate_limit_tracker[("tool1", "user1")] = [time.time()]
        _rate_limit_tracker[("tool2", "user2")] = [time.time()]

        with patch("src.domains.agents.utils.rate_limiting.logger"):
            reset_rate_limits()

        assert len(_rate_limit_tracker) == 0

    def test_reset_specific_tool_and_user(self):
        """Test resetting specific tool and user."""
        _rate_limit_tracker[("tool1", "user1")] = [time.time()]
        _rate_limit_tracker[("tool1", "user2")] = [time.time()]
        _rate_limit_tracker[("tool2", "user1")] = [time.time()]

        with patch("src.domains.agents.utils.rate_limiting.logger"):
            reset_rate_limits(tool_name="tool1", user_id="user1")

        # Only tool1/user1 should be removed
        assert ("tool1", "user1") not in _rate_limit_tracker
        assert ("tool1", "user2") in _rate_limit_tracker
        assert ("tool2", "user1") in _rate_limit_tracker

    def test_reset_all_users_for_tool(self):
        """Test resetting all users for specific tool."""
        _rate_limit_tracker[("tool1", "user1")] = [time.time()]
        _rate_limit_tracker[("tool1", "user2")] = [time.time()]
        _rate_limit_tracker[("tool2", "user1")] = [time.time()]

        with patch("src.domains.agents.utils.rate_limiting.logger"):
            reset_rate_limits(tool_name="tool1")

        # All tool1 entries should be removed
        assert ("tool1", "user1") not in _rate_limit_tracker
        assert ("tool1", "user2") not in _rate_limit_tracker
        # tool2 should remain
        assert ("tool2", "user1") in _rate_limit_tracker

    def test_reset_all_tools_for_user(self):
        """Test resetting all tools for specific user."""
        _rate_limit_tracker[("tool1", "user1")] = [time.time()]
        _rate_limit_tracker[("tool2", "user1")] = [time.time()]
        _rate_limit_tracker[("tool1", "user2")] = [time.time()]

        with patch("src.domains.agents.utils.rate_limiting.logger"):
            reset_rate_limits(user_id="user1")

        # All user1 entries should be removed
        assert ("tool1", "user1") not in _rate_limit_tracker
        assert ("tool2", "user1") not in _rate_limit_tracker
        # user2 should remain
        assert ("tool1", "user2") in _rate_limit_tracker

    def test_reset_nonexistent_key(self):
        """Test resetting nonexistent key doesn't crash."""
        with patch("src.domains.agents.utils.rate_limiting.logger"):
            # Should not raise
            reset_rate_limits(tool_name="nonexistent", user_id="nonexistent")


# ============================================================================
# Tests for module interface
# ============================================================================


class TestModuleInterface:
    """Tests for module exports."""

    def test_all_exports(self):
        """Test that __all__ contains expected exports."""
        from src.domains.agents.utils import rate_limiting

        expected_exports = [
            "rate_limit",
            "get_rate_limit_status",
            "reset_rate_limits",
        ]

        for export in expected_exports:
            assert export in rate_limiting.__all__
            assert hasattr(rate_limiting, export)
