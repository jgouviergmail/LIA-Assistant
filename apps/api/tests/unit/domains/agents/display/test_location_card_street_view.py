"""LocationCard street-view thumbnail (lot SV, 2026-08).

The producer only sets ``street_view_url`` when the FREE metadata endpoint
confirmed imagery exists, so the card renders it unconditionally when present
(and renders nothing extra when absent).
"""

from __future__ import annotations

import pytest

from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.location_card import LocationCard

pytestmark = pytest.mark.unit

_DATA = {
    "formatted_address": "5 Avenue Anatole France, 75007 Paris",
    "locality": "Paris",
    "country": "France",
    "latitude": 48.8584,
    "longitude": 2.2945,
    "static_map_url": "/api/v1/connectors/google-location/static-map?lat=48.8584&lng=2.2945",
}


@pytest.fixture
def card() -> LocationCard:
    return LocationCard()


@pytest.fixture
def ctx() -> RenderContext:
    return RenderContext(language="fr")


class TestStreetViewThumbnail:
    def test_street_view_image_renders_when_url_present(
        self, card: LocationCard, ctx: RenderContext
    ) -> None:
        html = card.render(
            {**_DATA, "street_view_url": "/api/v1/connectors/street-view?location=48.8584,2.2945"},
            ctx,
            with_wrapper=False,
        )
        assert "/api/v1/connectors/street-view?location=48.8584,2.2945" in html
        # Same visual language as the map hero (charte integration).
        assert html.count("lia-route__map-image") == 2

    def test_no_street_view_section_when_absent(
        self, card: LocationCard, ctx: RenderContext
    ) -> None:
        html = card.render(dict(_DATA), ctx, with_wrapper=False)
        assert "street-view" not in html
        assert html.count("lia-route__map-image") == 1
