"""
Unit tests for _emit_progressive_screenshot() from browser_tools.py.

Validates the progressive screenshot emission logic including debouncing,
feature-flag gating, side-channel queue delivery, and browser_screenshot_store
integration.

Phase: evolution — Browser Progressive Screenshots
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.agents.tools.browser_tools import (
    _emit_progressive_screenshot,
    _screenshot_debounce,
)

# ============================================================================
# FIXTURES
# ============================================================================

FAKE_FULL_RES = b"\xff\xd8\xff\xe0" + b"\x00" * 1000  # Fake JPEG header + padding
FAKE_THUMBNAIL = b"\xff\xd8\xff\xe0" + b"\x00" * 200


@pytest.fixture(autouse=True)
def _clear_debounce() -> None:
    """Clear the debounce dict before each test to prevent cross-test leaks."""
    _screenshot_debounce.clear()


def _make_runtime(
    queue: object | None = None,
    user_id: str = "test-user-123",
    thread_id: str = "conv-456",
    parent_thread_id: str | None = None,
) -> MagicMock:
    """Create a mock ToolRuntime with configurable dict.

    Args:
        queue: The side-channel queue (or None to omit).
        user_id: User ID in configurable.
        thread_id: Thread ID in configurable.
        parent_thread_id: Parent thread ID (forwarded from parent graph).

    Returns:
        Mock runtime with .config attribute.
    """
    configurable: dict = {
        "user_id": user_id,
        "thread_id": thread_id,
    }
    if queue is not None:
        configurable["__side_channel_queue"] = queue
    if parent_thread_id is not None:
        configurable["__parent_thread_id"] = parent_thread_id
    runtime = MagicMock()
    runtime.config = {"configurable": configurable}
    return runtime


def _make_session(
    full_res: bytes | None = FAKE_FULL_RES,
    thumbnail: bytes | None = FAKE_THUMBNAIL,
) -> AsyncMock:
    """Create a mock browser session with screenshot_with_thumbnail().

    Args:
        full_res: Full-resolution bytes to return.
        thumbnail: Thumbnail bytes to return.

    Returns:
        AsyncMock session.
    """
    session = AsyncMock()
    session.screenshot_with_thumbnail = AsyncMock(return_value=(full_res, thumbnail))
    return session


# ============================================================================
# TESTS
# ============================================================================


class TestEmitProgressiveScreenshot:
    """Tests for _emit_progressive_screenshot()."""

    @pytest.mark.asyncio
    @patch("src.domains.agents.tools.browser_tools.settings")
    async def test_puts_screenshot_in_queue_when_enabled(self, mock_settings: MagicMock) -> None:
        """Puts a ChatStreamChunk in the queue when feature is enabled."""
        mock_settings.browser_progressive_screenshots = True
        mock_settings.browser_screenshot_debounce_seconds = 0.5
        queue = MagicMock()
        runtime = _make_runtime(queue=queue)
        session = _make_session()

        await _emit_progressive_screenshot(runtime, session, "https://example.com", "Example")

        queue.put_nowait.assert_called_once()
        chunk = queue.put_nowait.call_args[0][0]
        assert chunk.type == "browser_screenshot"
        assert chunk.content["url"] == "https://example.com"
        assert chunk.content["title"] == "Example"
        assert "image_base64" in chunk.content

    @pytest.mark.asyncio
    @patch("src.domains.agents.tools.browser_tools.settings")
    async def test_noop_when_feature_disabled(self, mock_settings: MagicMock) -> None:
        """No-op when browser_progressive_screenshots setting is False."""
        mock_settings.browser_progressive_screenshots = False
        queue = MagicMock()
        runtime = _make_runtime(queue=queue)
        session = _make_session()

        await _emit_progressive_screenshot(runtime, session, "https://example.com", "Example")

        queue.put_nowait.assert_not_called()
        session.screenshot_with_thumbnail.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.domains.agents.tools.browser_tools.settings")
    async def test_noop_when_queue_missing(self, mock_settings: MagicMock) -> None:
        """No-op when __side_channel_queue is not in configurable."""
        mock_settings.browser_progressive_screenshots = True
        mock_settings.browser_screenshot_debounce_seconds = 0.5
        runtime = _make_runtime(queue=None)  # No queue
        session = _make_session()

        await _emit_progressive_screenshot(runtime, session, "https://example.com", "Example")

        session.screenshot_with_thumbnail.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.domains.agents.tools.browser_tools.time")
    @patch("src.domains.agents.tools.browser_tools.settings")
    async def test_debounce_skips_rapid_calls(
        self, mock_settings: MagicMock, mock_time: MagicMock
    ) -> None:
        """Debounce skips emission when called too rapidly (within interval)."""
        mock_settings.browser_progressive_screenshots = True
        mock_settings.browser_screenshot_debounce_seconds = 0.5
        queue = MagicMock()
        runtime = _make_runtime(queue=queue, user_id="user-debounce")
        session = _make_session()

        # First call at t=100.0
        mock_time.monotonic.return_value = 100.0
        await _emit_progressive_screenshot(runtime, session, "https://a.com", "A")
        assert queue.put_nowait.call_count == 1

        # Second call at t=100.2 (within debounce window of 0.5s)
        mock_time.monotonic.return_value = 100.2
        await _emit_progressive_screenshot(runtime, session, "https://b.com", "B")
        # Should still be 1 — second call was debounced
        assert queue.put_nowait.call_count == 1

    @pytest.mark.asyncio
    @patch("src.domains.agents.tools.browser_tools.time")
    @patch("src.domains.agents.tools.browser_tools.settings")
    async def test_debounce_allows_after_interval(
        self, mock_settings: MagicMock, mock_time: MagicMock
    ) -> None:
        """Debounce allows emission after the interval has elapsed."""
        mock_settings.browser_progressive_screenshots = True
        mock_settings.browser_screenshot_debounce_seconds = 0.5
        queue = MagicMock()
        runtime = _make_runtime(queue=queue, user_id="user-debounce-2")
        session = _make_session()

        # First call at t=100.0
        mock_time.monotonic.return_value = 100.0
        await _emit_progressive_screenshot(runtime, session, "https://a.com", "A")
        assert queue.put_nowait.call_count == 1

        # Second call at t=100.6 (after 0.5s debounce interval)
        mock_time.monotonic.return_value = 100.6
        await _emit_progressive_screenshot(runtime, session, "https://b.com", "B")
        assert queue.put_nowait.call_count == 2

    @pytest.mark.asyncio
    @patch("src.domains.agents.tools.browser_tools.settings")
    async def test_noop_when_screenshot_returns_none(self, mock_settings: MagicMock) -> None:
        """No-op when screenshot_with_thumbnail() returns (None, None)."""
        mock_settings.browser_progressive_screenshots = True
        mock_settings.browser_screenshot_debounce_seconds = 0.5
        queue = MagicMock()
        runtime = _make_runtime(queue=queue)
        session = _make_session(full_res=None, thumbnail=None)

        await _emit_progressive_screenshot(runtime, session, "https://example.com", "Example")

        queue.put_nowait.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.domains.agents.tools.browser_tools.settings")
    async def test_never_raises_on_any_error(self, mock_settings: MagicMock) -> None:
        """Never raises — silently handles any exception."""
        mock_settings.browser_progressive_screenshots = True
        mock_settings.browser_screenshot_debounce_seconds = 0.5
        queue = MagicMock()
        queue.put_nowait.side_effect = RuntimeError("Queue exploded")
        runtime = _make_runtime(queue=queue)
        session = _make_session()

        # Should not raise
        await _emit_progressive_screenshot(runtime, session, "https://example.com", "Example")

    @pytest.mark.asyncio
    @patch(
        "src.domains.agents.tools.browser_tools.store_last_browser_screenshot",
        create=True,
    )
    @patch("src.domains.agents.tools.browser_tools.settings")
    async def test_stores_full_res_in_browser_screenshot_store(
        self, mock_settings: MagicMock, mock_store: MagicMock
    ) -> None:
        """Stores full-res bytes in browser_screenshot_store for card finale."""
        mock_settings.browser_progressive_screenshots = True
        mock_settings.browser_screenshot_debounce_seconds = 0.5
        queue = MagicMock()
        runtime = _make_runtime(queue=queue, parent_thread_id="conv-final-123")
        session = _make_session()

        # Patch the lazy import inside the function
        with patch(
            "src.domains.agents.tools.browser_screenshot_store.store_last_browser_screenshot"
        ) as patched_store:
            await _emit_progressive_screenshot(runtime, session, "https://example.com", "Example")
            patched_store.assert_called_once_with("conv-final-123", FAKE_FULL_RES)

    @pytest.mark.asyncio
    @patch("src.domains.agents.tools.browser_tools.settings")
    async def test_noop_when_runtime_is_none(self, mock_settings: MagicMock) -> None:
        """No-op when runtime is None (graceful degradation)."""
        mock_settings.browser_progressive_screenshots = True
        mock_settings.browser_screenshot_debounce_seconds = 0.5
        session = _make_session()

        # Should not raise
        await _emit_progressive_screenshot(None, session, "https://example.com", "Example")

    @pytest.mark.asyncio
    @patch("src.domains.agents.tools.browser_tools.settings")
    async def test_screenshot_session_exception_handled(self, mock_settings: MagicMock) -> None:
        """Handles exceptions from session.screenshot_with_thumbnail() gracefully."""
        mock_settings.browser_progressive_screenshots = True
        mock_settings.browser_screenshot_debounce_seconds = 0.5
        queue = MagicMock()
        runtime = _make_runtime(queue=queue)
        session = AsyncMock()
        session.screenshot_with_thumbnail = AsyncMock(
            side_effect=RuntimeError("Playwright crashed")
        )

        # Should not raise
        await _emit_progressive_screenshot(runtime, session, "https://example.com", "Example")
        queue.put_nowait.assert_not_called()
