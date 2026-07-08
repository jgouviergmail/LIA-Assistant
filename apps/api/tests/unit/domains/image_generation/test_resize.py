"""Tests for image resizing utility (audit wave 3, item A6).

Covers template selection, resize behavior, and the async wrapper that
keeps Pillow's CPU-heavy decode/LANCZOS/encode work off the event loop.
"""

from __future__ import annotations

import base64
import io
import os

import pytest
from PIL import Image

from src.domains.image_generation.resize import (
    _best_template,
    resize_image_b64,
    resize_image_b64_async,
)
from tests.helpers.event_loop import assert_workload_off_loop

# Threshold for the event-loop stall assertion. A synchronous resize of the
# large test image takes several hundred ms; off-loop it stays far below this.
_MAX_ALLOWED_STALL_SECONDS = 0.15


def _make_image_b64(width: int, height: int, mode: str = "RGB") -> str:
    """Build a base64-encoded PNG test image of the given dimensions."""
    color = (200, 100, 50) if mode == "RGB" else (200, 100, 50, 128)
    img = Image.new(mode, (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


@pytest.mark.unit
class TestBestTemplate:
    """Template selection by aspect ratio."""

    def test_square_image_selects_square_template(self) -> None:
        assert _best_template(2000, 2000) == (1024, 1024)

    def test_landscape_image_selects_landscape_template(self) -> None:
        assert _best_template(3000, 2000) == (1536, 1024)

    def test_portrait_image_selects_portrait_template(self) -> None:
        assert _best_template(2000, 3000) == (1024, 1536)


@pytest.mark.unit
class TestResizeImageB64:
    """Synchronous resize behavior."""

    def test_large_image_resized_within_template(self) -> None:
        resized_b64, size_str = resize_image_b64(_make_image_b64(2048, 2048))
        assert size_str == "1024x1024"
        img = Image.open(io.BytesIO(base64.b64decode(resized_b64)))
        assert img.size == (1024, 1024)

    def test_small_image_passthrough(self) -> None:
        original = _make_image_b64(512, 512)
        resized_b64, size_str = resize_image_b64(original)
        assert resized_b64 == original
        assert size_str == "1024x1024"

    def test_rgba_converted_to_rgb(self) -> None:
        resized_b64, _ = resize_image_b64(_make_image_b64(2048, 2048, mode="RGBA"))
        img = Image.open(io.BytesIO(base64.b64decode(resized_b64)))
        assert img.mode == "RGB"


@pytest.mark.unit
class TestResizeImageB64Async:
    """Async wrapper keeps the event loop responsive."""

    async def test_matches_sync_result(self) -> None:
        source = _make_image_b64(2048, 1536)
        sync_result = resize_image_b64(source)
        async_result = await resize_image_b64_async(source)
        assert async_result == sync_result

    async def test_does_not_block_event_loop(self) -> None:
        """A CPU-heavy resize must not stall concurrent coroutines."""
        # Noise image: incompressible, so decode+LANCZOS+encode reliably
        # takes several hundred ms when run synchronously on the loop.
        noise = Image.frombytes("RGB", (3000, 3000), os.urandom(3000 * 3000 * 3))
        buf = io.BytesIO()
        noise.save(buf, format="PNG")
        source = base64.b64encode(buf.getvalue()).decode("ascii")

        resized_b64, size_str = await assert_workload_off_loop(
            lambda: resize_image_b64_async(source),
            blocking_baseline=lambda: resize_image_b64(source),
            absolute_threshold_seconds=_MAX_ALLOWED_STALL_SECONDS,
            context="resize",
        )

        assert size_str == "1024x1024"
        assert resized_b64
