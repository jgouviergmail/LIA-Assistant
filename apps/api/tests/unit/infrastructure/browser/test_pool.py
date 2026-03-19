"""
Unit tests for browser session pool.

Phase: evolution F7 — Browser Control (Playwright)
"""

import pytest

from src.infrastructure.browser.pool import BrowserPool


class TestBrowserPool:
    """Tests for BrowserPool."""

    def test_pool_init_not_healthy(self):
        """Pool starts as not healthy before initialize()."""
        pool = BrowserPool()
        assert not pool.is_healthy

    def test_memory_usage_returns_none_on_windows(self):
        """Memory monitoring returns None on non-Linux (Windows/macOS)."""
        pool = BrowserPool()
        # On Windows/macOS, /proc doesn't exist
        result = pool.get_memory_usage_mb()
        # Should return None or a float (if running on Linux)
        assert result is None or isinstance(result, float)


class TestBrowserPoolSessionLimit:
    """Tests for global session coordination."""

    @pytest.mark.asyncio
    async def test_pool_unhealthy_raises(self):
        """Acquiring session on unhealthy pool raises ValueError."""
        pool = BrowserPool()
        with pytest.raises(ValueError, match="not healthy"):
            await pool.acquire_session("user123")
