"""A Routes request is filed at the SKU Google bills it at.

Google bills the Routes API per request in three tiers, and the Route Matrix per
ELEMENT returned (developers.google.com/maps/billing-and-pricing/sku-details,
read 2026-09-23): Pro for a traffic-aware routing preference, an optimised
waypoint order, 11 to 25 intermediate waypoints or a location modifier;
Enterprise for two-wheeler routing, toll calculation or traffic on polylines.
LIA's default drive route asks for traffic-aware routing AND tolls -- the
Enterprise tier, $15 per 1000 -- and every such call was filed at the Essentials
price, $5, while a matrix was filed once whatever its size.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest

from src.core.config import settings
from src.domains.connectors.clients.google_routes_client import (
    ROUTES_SKU_SUFFIXES,
    GoogleRoutesClient,
    TravelMode,
    routes_sku_suffix,
)

pytestmark = pytest.mark.unit

_DRIVE = {"travelMode": "DRIVE", "routingPreference": "TRAFFIC_AWARE"}


@pytest.mark.parametrize(
    ("body", "suffix"),
    [
        ({**_DRIVE, "extraComputations": ["TOLLS"]}, ":enterprise"),
        ({"travelMode": "DRIVE", "extraComputations": ["TRAFFIC_ON_POLYLINE"]}, ":enterprise"),
        ({"travelMode": "TWO_WHEELER"}, ":enterprise"),
        (_DRIVE, ":pro"),
        ({**_DRIVE, "routingPreference": "TRAFFIC_AWARE_OPTIMAL"}, ":pro"),
        ({"travelMode": "WALK", "intermediates": [{}] * 11}, ":pro"),
        ({"travelMode": "BICYCLE", "intermediates": [{}], "optimizeWaypointOrder": True}, ":pro"),
        ({"travelMode": "WALK", "origin": {"address": "A", "vehicleStopover": True}}, ":pro"),
        ({"travelMode": "WALK", "intermediates": [{}] * 10}, ""),
        ({**_DRIVE, "routingPreference": "TRAFFIC_UNAWARE"}, ""),
        ({"travelMode": "WALK"}, ""),
        ({"travelMode": "TRANSIT"}, ""),
    ],
)
def test_a_request_is_filed_at_the_sku_its_features_trigger(
    body: dict[str, Any], suffix: str
) -> None:
    assert routes_sku_suffix(body) == suffix
    assert suffix in ROUTES_SKU_SUFFIXES


class _Response:
    status_code = 200

    def __init__(self, payload: Any) -> None:
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> Any:
        return self._payload


class _Http:
    """Answers every POST with one payload, as the provider would."""

    is_closed = False

    def __init__(self, payload: Any) -> None:
        self._payload = payload

    async def post(self, url: str, headers: dict[str, str], json: dict[str, Any]) -> _Response:
        return _Response(self._payload)


@pytest.fixture
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "google_api_key", "test-key")


@pytest.mark.usefixtures("_api_key")
async def test_the_default_drive_route_is_filed_at_the_enterprise_sku() -> None:
    client = GoogleRoutesClient()
    client._client = _Http({"routes": [{"distanceMeters": 1000}]})

    with patch(
        "src.domains.connectors.clients.google_routes_client.track_google_api_call"
    ) as track:
        await client.compute_route(origin="A", destination="B", travel_mode=TravelMode.DRIVE)

    track.assert_called_once_with("routes", "/directions/v2:computeRoutes:enterprise", cached=False)


@pytest.mark.usefixtures("_api_key")
async def test_a_walking_route_stays_at_the_essentials_sku() -> None:
    client = GoogleRoutesClient()
    client._client = _Http({"routes": [{"distanceMeters": 1000}]})

    with patch(
        "src.domains.connectors.clients.google_routes_client.track_google_api_call"
    ) as track:
        await client.compute_route(origin="A", destination="B", travel_mode=TravelMode.WALK)

    track.assert_called_once_with("routes", "/directions/v2:computeRoutes", cached=False)


@pytest.mark.usefixtures("_api_key")
async def test_a_matrix_is_filed_once_per_element_returned() -> None:
    elements = [{"originIndex": o, "destinationIndex": d} for o in range(2) for d in range(3)]
    client = GoogleRoutesClient()
    client._client = _Http(elements)

    with patch(
        "src.domains.connectors.clients.google_routes_client.track_google_api_call"
    ) as track:
        await client.compute_route_matrix(
            origins=["A", "B"], destinations=["C", "D", "E"], travel_mode=TravelMode.DRIVE
        )

    track.assert_called_once_with(
        "routes", "/distanceMatrix/v2:computeRouteMatrix:pro", cached=False, units=6
    )
