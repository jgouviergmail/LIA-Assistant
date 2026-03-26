"""
Unit tests for emit_side_channel_chunk() from runtime_helpers.py.

Validates the generic side-channel SSE emission mechanism that allows any tool
to emit ChatStreamChunk events directly to the frontend without going through
the LLM response.

Phase: evolution — Browser Progressive Screenshots
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from src.domains.agents.tools.runtime_helpers import emit_side_channel_chunk

# ============================================================================
# FIXTURES
# ============================================================================


def _make_runtime(configurable: dict | None = None) -> MagicMock:
    """Create a mock ToolRuntime with a config dict.

    Args:
        configurable: Dict to put under runtime.config["configurable"].

    Returns:
        Mock runtime with .config attribute.
    """
    runtime = MagicMock()
    runtime.config = {"configurable": configurable} if configurable is not None else {}
    return runtime


def _make_chunk(chunk_type: str = "browser_screenshot") -> MagicMock:
    """Create a mock ChatStreamChunk.

    Args:
        chunk_type: The type field value for the chunk.

    Returns:
        Mock chunk object.
    """
    chunk = MagicMock()
    chunk.type = chunk_type
    return chunk


# ============================================================================
# TESTS
# ============================================================================


class TestEmitSideChannelChunk:
    """Tests for emit_side_channel_chunk()."""

    def test_puts_chunk_in_queue(self) -> None:
        """Puts chunk in queue when __side_channel_queue exists in configurable."""
        queue = MagicMock()
        runtime = _make_runtime({"__side_channel_queue": queue})
        chunk = _make_chunk()

        emit_side_channel_chunk(runtime, chunk)

        queue.put_nowait.assert_called_once_with(chunk)

    def test_noop_when_queue_not_in_configurable(self) -> None:
        """No-op when __side_channel_queue is missing from configurable dict."""
        runtime = _make_runtime({"user_id": "test-user"})
        chunk = _make_chunk()

        # Should not raise
        emit_side_channel_chunk(runtime, chunk)

    def test_noop_when_configurable_is_none(self) -> None:
        """No-op when configurable key returns None."""
        runtime = MagicMock()
        runtime.config = {"configurable": None}
        chunk = _make_chunk()

        emit_side_channel_chunk(runtime, chunk)

    def test_noop_when_runtime_is_none(self) -> None:
        """No-op when runtime is None."""
        chunk = _make_chunk()

        # Should not raise
        emit_side_channel_chunk(None, chunk)

    def test_never_raises_on_full_queue(self) -> None:
        """Never raises when queue.put_nowait() raises (e.g., full queue)."""
        queue = MagicMock()
        queue.put_nowait.side_effect = asyncio.QueueFull()
        runtime = _make_runtime({"__side_channel_queue": queue})
        chunk = _make_chunk()

        # Should not raise
        emit_side_channel_chunk(runtime, chunk)

    def test_never_raises_on_attribute_error(self) -> None:
        """Never raises on AttributeError (broken runtime object)."""
        runtime = MagicMock()
        runtime.config = MagicMock()
        runtime.config.get.side_effect = AttributeError("broken")
        chunk = _make_chunk()

        # Should not raise
        emit_side_channel_chunk(runtime, chunk)

    def test_never_raises_on_type_error(self) -> None:
        """Never raises on TypeError (unexpected config structure)."""
        runtime = MagicMock()
        runtime.config = "not_a_dict"
        chunk = _make_chunk()

        # Should not raise — try/except catches all
        emit_side_channel_chunk(runtime, chunk)

    def test_queue_receives_exact_chunk_object(self) -> None:
        """Queue receives the exact same chunk object passed in (no transformation)."""
        queue = MagicMock()
        runtime = _make_runtime({"__side_channel_queue": queue})
        chunk = _make_chunk("custom_type")

        emit_side_channel_chunk(runtime, chunk)

        received = queue.put_nowait.call_args[0][0]
        assert received is chunk
