"""Field-mask and SKU-tracking contract of GooglePlacesClient.

The field mask decides the billed SKU tier (Places API New bills by the
highest-tier field requested), so the mask IS a billing contract:

- full mode requests Enterprise + Atmosphere fields and must be tracked on
  the base endpoint;
- lite mode must stay strictly within the Pro tier (no rating / hours /
  contact / atmosphere fields) and be tracked on the ``:lite`` endpoint so
  the pricing table can bill it at the Pro price;
- the Pro-tier identity fields added by the 2026-08 audit (businessStatus,
  primaryTypeDisplayName, priceRange, shortFormattedAddress) must be present
  so a permanently-closed place can never render as a normal one.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.clients.google_places_client import GooglePlacesClient

pytestmark = pytest.mark.unit

# Fields whose presence in a mask escalates billing beyond the Pro tier
# (Enterprise: hours/contact/rating; Enterprise + Atmosphere: reviews etc.).
_BEYOND_PRO_FIELDS = (
    "rating",
    "userRatingCount",
    "currentOpeningHours",
    "regularOpeningHours",
    "websiteUri",
    "nationalPhoneNumber",
    "internationalPhoneNumber",
    "reviews",
    "editorialSummary",
    "priceLevel",
)


@pytest.fixture
def client() -> GooglePlacesClient:
    return GooglePlacesClient(user_id=uuid4(), language="en")


@pytest.fixture
def request_spy(client: GooglePlacesClient) -> AsyncMock:
    spy = AsyncMock(return_value={"places": []})
    client._make_request = spy  # type: ignore[method-assign]
    return spy


def _mask_of(spy: AsyncMock) -> list[str]:
    headers = spy.call_args.kwargs["extra_headers"]
    return headers["X-Goog-FieldMask"].split(",")


class TestSearchTextMasks:
    async def test_full_mask_includes_pro_identity_fields(
        self, client: GooglePlacesClient, request_spy: AsyncMock
    ) -> None:
        await client.search_text("pizza", use_cache=False)
        mask = _mask_of(request_spy)
        assert "places.businessStatus" in mask
        assert "places.primaryTypeDisplayName" in mask

    async def test_full_mode_tracks_base_endpoint(
        self, client: GooglePlacesClient, request_spy: AsyncMock
    ) -> None:
        with patch(
            "src.domains.connectors.clients.google_places_client.track_google_api_call"
        ) as tracker:
            await client.search_text("pizza", use_cache=False)
        tracker.assert_any_call("places", "/places:searchText", cached=False)

    async def test_lite_mask_stays_within_pro_tier(
        self, client: GooglePlacesClient, request_spy: AsyncMock
    ) -> None:
        await client.search_text("pizza", use_cache=False, detail_level="lite")
        mask = _mask_of(request_spy)
        for field in _BEYOND_PRO_FIELDS:
            assert f"places.{field}" not in mask, f"lite mask escalates billing via {field}"
        # Lite still carries identity + status (Pro tier).
        assert "places.businessStatus" in mask
        assert "places.displayName" in mask

    async def test_lite_mode_tracks_lite_endpoint(
        self, client: GooglePlacesClient, request_spy: AsyncMock
    ) -> None:
        with patch(
            "src.domains.connectors.clients.google_places_client.track_google_api_call"
        ) as tracker:
            await client.search_text("pizza", use_cache=False, detail_level="lite")
        tracker.assert_any_call("places", "/places:searchText:lite", cached=False)


class TestSearchNearbyMasks:
    async def test_full_mask_includes_pro_identity_fields(
        self, client: GooglePlacesClient, request_spy: AsyncMock
    ) -> None:
        await client.search_nearby(latitude=48.85, longitude=2.35, use_cache=False)
        mask = _mask_of(request_spy)
        assert "places.businessStatus" in mask
        assert "places.primaryTypeDisplayName" in mask

    async def test_lite_mask_stays_within_pro_tier_and_tracks_lite(
        self, client: GooglePlacesClient, request_spy: AsyncMock
    ) -> None:
        with patch(
            "src.domains.connectors.clients.google_places_client.track_google_api_call"
        ) as tracker:
            await client.search_nearby(
                latitude=48.85, longitude=2.35, use_cache=False, detail_level="lite"
            )
        mask = _mask_of(request_spy)
        for field in _BEYOND_PRO_FIELDS:
            assert f"places.{field}" not in mask, f"lite mask escalates billing via {field}"
        tracker.assert_any_call("places", "/places:searchNearby:lite", cached=False)


class TestPlaceDetailsMask:
    async def test_details_mask_includes_audit_added_fields(
        self, client: GooglePlacesClient
    ) -> None:
        spy = AsyncMock(return_value={"id": "x"})
        client._make_request = spy  # type: ignore[method-assign]
        await client.get_place_details("place-id-1", use_cache=False)
        mask = _mask_of(spy)
        for field in (
            "businessStatus",
            "priceRange",
            "primaryTypeDisplayName",
            "shortFormattedAddress",
        ):
            assert field in mask, f"details mask misses {field}"


class TestLiteCacheIsolation:
    async def test_lite_and_full_search_use_distinct_cache_keys(
        self, client: GooglePlacesClient, request_spy: AsyncMock
    ) -> None:
        """A cached lite result must never be served to a full-mode request."""
        cache = AsyncMock()
        cache.get_search = AsyncMock(return_value=(None, False, None, None))
        cache.set_search = AsyncMock()
        with patch.object(GooglePlacesClient, "_get_cache", new=AsyncMock(return_value=cache)):
            request_spy.return_value = {"places": [{"id": "a"}]}
            await client.search_text("pizza", use_cache=True)
            await client.search_text("pizza", use_cache=True, detail_level="lite")

        def _detail_level_of(call: Any) -> str | None:
            return call.kwargs.get("detail_level")

        levels_read = [_detail_level_of(c) for c in cache.get_search.call_args_list]
        levels_written = [_detail_level_of(c) for c in cache.set_search.call_args_list]
        assert "lite" in levels_read, "lite reads must be keyed by detail_level"
        assert "lite" in levels_written, "lite writes must be keyed by detail_level"
