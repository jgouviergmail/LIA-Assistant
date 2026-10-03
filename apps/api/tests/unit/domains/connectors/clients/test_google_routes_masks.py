"""Actual HTTP request masks preserve the ordered-waypoint contract and SKU."""

import json
from unittest.mock import patch

import httpx
import pytest

from src.core.config import settings
from src.domains.connectors.clients.google_routes_client import GoogleRoutesClient, TravelMode

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("optimized", [False, True])
async def test_optimized_waypoint_request_includes_its_required_response_index(
    monkeypatch, optimized
):
    monkeypatch.setattr(settings, "google_api_key", "test-key")
    requests: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"routes": []})

    client = GoogleRoutesClient()
    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as http:
        client._client = http
        with patch("src.domains.connectors.clients.google_routes_client.track_google_api_call"):
            await client.compute_route(
                "A",
                "B",
                travel_mode=TravelMode.BICYCLE,
                waypoints=["S1", "S2"],
                optimize_waypoint_order=optimized,
            )
    assert len(requests) == 1
    body = json.loads(requests[0].content)
    mask = requests[0].headers["X-Goog-FieldMask"].split(",")
    assert ("routes.optimizedIntermediateWaypointIndex" in mask) is optimized
    assert body.get("optimizeWaypointOrder", False) is optimized
