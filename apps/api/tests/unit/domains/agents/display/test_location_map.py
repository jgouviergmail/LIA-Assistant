"""Received addresses gain one optional map while retaining all static facts."""

import html
import json
import re
from unittest.mock import patch

import pytest

from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.location_card import LocationCard
from src.domains.agents.display.components.location_map import (
    location_map_point,
    render_location_map,
)

pytestmark = pytest.mark.unit


def test_location_preserves_static_map_street_view_and_zero_coordinate() -> None:
    """The new display projection does not replace the original image modules."""
    rendered = LocationCard().render(
        {
            "latitude": 0,
            "longitude": 0,
            "formatted_address": "A < B & C",
            "locality": "Equator",
            "static_map_url": "/api/v1/static-map",
            "street_view_url": "/api/v1/street-view",
        },
        RenderContext(language="en"),
        with_wrapper=False,
    )
    matched = re.search(r'data-location-map="([^"]+)"', rendered)
    assert matched is not None
    assert json.loads(html.unescape(matched[1])) == {
        "version": 1,
        "label": "Equator",
        "address": "A < B & C",
        "position": {"lat": 0.0, "lng": 0.0},
    }
    assert rendered.count("lia-route__map-image") == 2
    assert "lia-location" in rendered
    assert rendered.count("<dd>0.000000</dd>") == 2
    assert "<dt>Latitude</dt>" in rendered
    assert "<dt>Longitude</dt>" in rendered
    assert "https://www.google.com/maps/@0.0,0.0,15z" in rendered
    assert "A &lt; B &amp; C" in rendered


def test_address_label_keeps_whole_facts_without_inventing_a_street_number() -> None:
    """The new label uses the supplied locality and keeps the address literal."""
    address = "12 bis <North>, Building B, Floor 4 — 京都"
    rendered = LocationCard().render(
        {
            "formatted_address": address,
            "locality": "Kyoto <east>",
            "country": "Japan",
            "postal_code": "600-8000",
        },
        RenderContext(language="en"),
        with_wrapper=False,
    )
    assert html.escape(address) in rendered
    assert "Kyoto &lt;east&gt;" in rendered
    assert "Japan" in rendered
    assert "600-8000" in rendered
    assert "data-location-map" not in rendered
    assert "lia-location__coordinates" not in rendered
    assert "<dd>0.000000</dd>" not in rendered


def test_address_without_locality_is_not_split_into_inferred_parts() -> None:
    """A missing town does not justify promoting a parsed address fragment."""
    address = "12 bis North, Building B, Floor 4"
    rendered = LocationCard().render(
        {"formatted_address": address}, RenderContext(language="en"), with_wrapper=False
    )
    title = re.search(r'<h3 class="lia-card-top__title">(.*?)</h3>', rendered)
    assert title is not None
    assert address in title[1]


@pytest.mark.parametrize("latitude", [None, True, "0", 91, -91, float("nan"), float("inf")])
def test_invalid_coordinates_keep_the_static_fallback(latitude: object) -> None:
    """Malformed geometry never suppresses a usable received image."""
    point = location_map_point(latitude, 0)
    assert point is None
    assert render_location_map(point, "Address", "Full address", "STATIC") == "STATIC"


def test_overlong_labels_do_not_truncate_address_facts() -> None:
    """A projection refusal leaves the source untouched rather than shortening it."""
    point = location_map_point(0, 0)
    assert render_location_map(point, "x" * 201, "Address", "STATIC") == "STATIC"
    assert render_location_map(point, "Place", "x" * 1001, "STATIC") == "STATIC"


def test_current_location_producer_keeps_a_valid_zero_static_map() -> None:
    """The real producer preserves zero through registry serialization and rendering."""
    from src.domains.agents.tools.places_tools import GetCurrentLocationTool

    with patch(
        "src.domains.agents.tools.places_tools.with_attribution", side_effect=lambda value: value
    ):
        result = GetCurrentLocationTool().format_registry_response(
            {
                "success": True,
                "data": {"formatted_address": "Equator", "location": {"lat": 0.0, "lon": 0.0}},
            }
        )
    assert result.registry_updates is not None
    item = next(iter(result.registry_updates.values()))
    payload = json.loads(item.model_dump_json())["payload"]
    assert payload["static_map_url"].endswith("lat=0.0&lng=0.0")
    rendered = LocationCard().render(payload, RenderContext(language="en"), with_wrapper=False)
    assert "data-location-map=" in rendered
    assert "lia-route__map-image" in rendered


@pytest.mark.parametrize("location", [None, {}, {"lat": 0}, {"lat": 0, "lon": None}])
def test_missing_coordinates_never_become_a_fabricated_zero_point(location: object) -> None:
    """A malformed success cannot gain a dynamic map at the default origin."""
    from src.domains.agents.tools.places_tools import GetCurrentLocationTool

    output = GetCurrentLocationTool().format_registry_response(
        {"success": True, "data": {"formatted_address": "Unknown", "location": location}}
    )
    assert output.success is False
    assert output.error_code == "INVALID_RESPONSE_FORMAT"
    assert not output.registry_updates
