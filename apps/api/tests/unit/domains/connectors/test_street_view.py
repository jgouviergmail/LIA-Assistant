"""Street View thumbnail availability helper (lot SV, 2026-08).

The metadata endpoint is FREE and answers "is there imagery here?" — the
helper only hands out a proxy URL when imagery exists, so cards never render
a broken or grey placeholder image. The billed image call happens later,
through the authenticated proxy endpoint, only when a card actually loads it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.domains.connectors.street_view import street_view_thumbnail_url

pytestmark = pytest.mark.unit


def _patch_metadata(payload: dict | Exception) -> object:
    mock = (
        AsyncMock(side_effect=payload)
        if isinstance(payload, Exception)
        else AsyncMock(return_value=payload)
    )
    return patch("src.domains.connectors.street_view._fetch_metadata", new=mock)


def _patch_enabled(value: bool) -> object:
    return patch("src.domains.connectors.street_view._street_view_enabled", return_value=value)


class TestStreetViewThumbnailUrl:
    async def test_available_imagery_yields_proxy_url(self) -> None:
        with _patch_enabled(True), _patch_metadata({"status": "OK"}):
            url = await street_view_thumbnail_url(48.8584, 2.2945)
        assert url == "/api/v1/connectors/street-view?location=48.8584,2.2945"

    async def test_no_imagery_yields_none(self) -> None:
        with _patch_enabled(True), _patch_metadata({"status": "ZERO_RESULTS"}):
            assert await street_view_thumbnail_url(0.0, 0.0) is None

    async def test_disabled_flag_short_circuits_without_io(self) -> None:
        fetch = AsyncMock()
        with (
            _patch_enabled(False),
            patch("src.domains.connectors.street_view._fetch_metadata", new=fetch),
        ):
            assert await street_view_thumbnail_url(48.85, 2.29) is None
        fetch.assert_not_awaited()

    async def test_metadata_error_is_fail_quiet(self) -> None:
        """Metadata being down must never break the card — just no thumbnail."""
        with _patch_enabled(True), _patch_metadata(TimeoutError("slow")):
            assert await street_view_thumbnail_url(48.85, 2.29) is None

    async def test_metadata_call_is_tracked_at_zero_cost(self) -> None:
        with (
            _patch_enabled(True),
            _patch_metadata({"status": "OK"}),
            patch("src.domains.connectors.street_view.track_google_api_call") as tracker,
        ):
            await street_view_thumbnail_url(48.85, 2.29)
        tracker.assert_called_once_with("street_view", "/streetview/metadata", cached=False)
