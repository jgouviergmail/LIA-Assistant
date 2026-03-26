"""
Unit tests for BrowserSession.screenshot_with_thumbnail().

Validates the dual-output screenshot method that produces both a full-resolution
JPEG and a reduced thumbnail for SSE side-channel streaming.

Phase: evolution — Browser Progressive Screenshots
"""

from __future__ import annotations

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from src.core.constants import BROWSER_SCREENSHOT_THUMBNAIL_WIDTH
from src.infrastructure.browser.session import BrowserSession

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture()
def jpeg_1280x720() -> bytes:
    """Create a real 1280x720 JPEG image using Pillow.

    Returns:
        Valid JPEG bytes at 1280x720 resolution.
    """
    img = Image.new("RGB", (1280, 720), color=(100, 149, 237))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


@pytest.fixture()
def mock_session() -> BrowserSession:
    """Create a BrowserSession with mocked Playwright internals.

    Returns:
        BrowserSession with mock context/page, no real browser required.
    """
    context = MagicMock()
    security = MagicMock()
    session = BrowserSession(user_id="test-user-1234", context=context, security=security)
    return session


def _make_page(jpeg_bytes: bytes, *, is_closed: bool = False) -> MagicMock:
    """Create a mock Playwright Page with sync is_closed() and async screenshot().

    Playwright's Page.is_closed() is synchronous, so we use MagicMock (not AsyncMock)
    to avoid returning a coroutine. The screenshot() method is async.

    Args:
        jpeg_bytes: JPEG bytes to return from screenshot().
        is_closed: Whether is_closed() should return True.

    Returns:
        MagicMock page with correct sync/async method signatures.
    """
    page = MagicMock()
    page.is_closed.return_value = is_closed
    page.screenshot = AsyncMock(return_value=jpeg_bytes)
    return page


# ============================================================================
# TESTS
# ============================================================================


class TestScreenshotWithThumbnail:
    """Tests for BrowserSession.screenshot_with_thumbnail()."""

    @pytest.mark.asyncio
    async def test_returns_tuple_of_bytes(
        self, mock_session: BrowserSession, jpeg_1280x720: bytes
    ) -> None:
        """Returns a tuple of (full_res, thumbnail) with correct types."""
        mock_session.page = _make_page(jpeg_1280x720)

        full_res, thumbnail = await mock_session.screenshot_with_thumbnail()

        assert isinstance(full_res, bytes)
        assert isinstance(thumbnail, bytes)

    @pytest.mark.asyncio
    async def test_thumbnail_smaller_than_full_res(
        self, mock_session: BrowserSession, jpeg_1280x720: bytes
    ) -> None:
        """Thumbnail byte size is smaller than full-res byte size."""
        mock_session.page = _make_page(jpeg_1280x720)

        full_res, thumbnail = await mock_session.screenshot_with_thumbnail()

        assert full_res is not None
        assert thumbnail is not None
        assert len(thumbnail) < len(full_res)

    @pytest.mark.asyncio
    async def test_thumbnail_width_matches_constant(
        self, mock_session: BrowserSession, jpeg_1280x720: bytes
    ) -> None:
        """Thumbnail width equals BROWSER_SCREENSHOT_THUMBNAIL_WIDTH (640)."""
        mock_session.page = _make_page(jpeg_1280x720)

        _, thumbnail = await mock_session.screenshot_with_thumbnail()

        assert thumbnail is not None
        thumb_img = Image.open(BytesIO(thumbnail))
        assert thumb_img.width == BROWSER_SCREENSHOT_THUMBNAIL_WIDTH

    @pytest.mark.asyncio
    async def test_thumbnail_preserves_aspect_ratio(
        self, mock_session: BrowserSession, jpeg_1280x720: bytes
    ) -> None:
        """Thumbnail preserves original aspect ratio (16:9)."""
        mock_session.page = _make_page(jpeg_1280x720)

        _, thumbnail = await mock_session.screenshot_with_thumbnail()

        assert thumbnail is not None
        thumb_img = Image.open(BytesIO(thumbnail))
        # Original is 1280x720 (16:9), thumbnail at 640px wide should be 640x360
        assert thumb_img.width == 640
        assert thumb_img.height == 360

    @pytest.mark.asyncio
    async def test_returns_none_none_when_page_is_none(self, mock_session: BrowserSession) -> None:
        """Returns (None, None) when page is None."""
        mock_session.page = None

        full_res, thumbnail = await mock_session.screenshot_with_thumbnail()

        assert full_res is None
        assert thumbnail is None

    @pytest.mark.asyncio
    async def test_returns_none_none_when_page_is_closed(
        self, mock_session: BrowserSession, jpeg_1280x720: bytes
    ) -> None:
        """Returns (None, None) when page.is_closed() is True."""
        mock_session.page = _make_page(jpeg_1280x720, is_closed=True)

        full_res, thumbnail = await mock_session.screenshot_with_thumbnail()

        assert full_res is None
        assert thumbnail is None

    @pytest.mark.asyncio
    async def test_returns_none_none_on_playwright_exception(
        self, mock_session: BrowserSession
    ) -> None:
        """Returns (None, None) when Playwright screenshot raises an exception."""
        page = MagicMock()
        page.is_closed.return_value = False
        page.screenshot = AsyncMock(side_effect=RuntimeError("Page crashed"))
        mock_session.page = page

        full_res, thumbnail = await mock_session.screenshot_with_thumbnail()

        assert full_res is None
        assert thumbnail is None

    @pytest.mark.asyncio
    async def test_full_res_is_valid_jpeg(
        self, mock_session: BrowserSession, jpeg_1280x720: bytes
    ) -> None:
        """Full-res output is a valid JPEG image."""
        mock_session.page = _make_page(jpeg_1280x720)

        full_res, _ = await mock_session.screenshot_with_thumbnail()

        assert full_res is not None
        img = Image.open(BytesIO(full_res))
        assert img.format == "JPEG"

    @pytest.mark.asyncio
    async def test_thumbnail_is_valid_jpeg(
        self, mock_session: BrowserSession, jpeg_1280x720: bytes
    ) -> None:
        """Thumbnail output is a valid JPEG image."""
        mock_session.page = _make_page(jpeg_1280x720)

        _, thumbnail = await mock_session.screenshot_with_thumbnail()

        assert thumbnail is not None
        img = Image.open(BytesIO(thumbnail))
        assert img.format == "JPEG"
