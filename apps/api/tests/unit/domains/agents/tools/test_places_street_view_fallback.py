"""Street View hero fallback on place details (lot SV, 2026-08).

A place without Places photos gets a Street View thumbnail as its card hero
(when imagery exists) — and a place WITH photos never triggers the metadata
call (no wasted request).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.tools.places_environment import apply_street_view_fallback

pytestmark = pytest.mark.unit


class TestStreetViewFallback:
    async def test_place_without_photo_gets_street_view_hero(self) -> None:
        details = {"name": "X", "location": {"lat": 48.85, "lon": 2.29}}
        with patch(
            "src.domains.connectors.street_view.street_view_thumbnail_url",
            new=AsyncMock(return_value="/api/v1/connectors/street-view?location=48.85,2.29"),
        ):
            await apply_street_view_fallback(details)
        assert details["photo_url"] == "/api/v1/connectors/street-view?location=48.85,2.29"

    async def test_place_with_photo_never_calls_metadata(self) -> None:
        details = {"name": "X", "photo_url": "/photo/1", "location": {"lat": 48.85, "lon": 2.29}}
        helper = AsyncMock()
        with patch("src.domains.connectors.street_view.street_view_thumbnail_url", new=helper):
            await apply_street_view_fallback(details)
        helper.assert_not_awaited()
        assert details["photo_url"] == "/photo/1"

    async def test_no_coordinates_or_no_imagery_leaves_details_unchanged(self) -> None:
        no_coords = {"name": "X"}
        with patch(
            "src.domains.connectors.street_view.street_view_thumbnail_url",
            new=AsyncMock(return_value=None),
        ):
            await apply_street_view_fallback(no_coords)
            with_coords = {"name": "X", "location": {"lat": 1.0, "lon": 2.0}}
            await apply_street_view_fallback(with_coords)
        assert "photo_url" not in no_coords
        assert "photo_url" not in with_coords
