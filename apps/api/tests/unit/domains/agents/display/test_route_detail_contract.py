"""Routes provider -> semantic projection -> serialized registry -> full card."""

from urllib.parse import parse_qs, urlsplit

import pytest

from src.core.config import settings
from src.domains.agents.data_registry.card_payload import card_payload
from src.domains.agents.data_registry.models import RegistryItem
from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.route_card import RouteCard
from src.domains.agents.tools.routes_tools import (
    _create_route_registry_item,
    _format_route_response,
)
from src.domains.connectors.clients.google_routes_client import TravelMode

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("value", [None, {}, "bad", [None]])
def test_malformed_provider_route_list_returns_a_recoverable_failure(value):
    output = formatted({"routes": value})
    assert output["success"] is False


def test_polyline_and_signed_media_are_excluded_from_the_canonical_route():
    output = formatted(route_response())
    route = output["data"]["route"]
    route["polyline"] = "HEAVY_POLYLINE"
    route["static_map_url"] = "/api/v1/connectors/google-routes/static-map?polyline=HEAVY_POLYLINE"
    _, item = _create_route_registry_item(output, "A", "B", TravelMode.DRIVE)
    assert "polyline" not in item.payload
    assert "static_map_url" not in item.payload
    assert card_payload(item)["polyline"] == "HEAVY_POLYLINE"


def test_exact_alternative_geometries_survive_registry_round_trip_outside_model_payload():
    from src.domains.agents.utils.polyline import encode_polyline

    raw = route_response(1)
    first = encode_polyline([(0, 0), (1, 1)])
    other = encode_polyline([(0, 0), (2, 2)])
    raw["routes"][0]["polyline"] = {"encodedPolyline": first}
    raw["routes"].append(
        {"distanceMeters": 0, "duration": "0s", "polyline": {"encodedPolyline": other}}
    )
    _, item = _create_route_registry_item(formatted(raw), "A", "B", TravelMode.DRIVE)
    restored = RegistryItem.model_validate_json(item.model_dump_json())
    geometry = card_payload(restored)["route_map"]
    assert geometry["primary_id"] == "route-0"
    assert [entry["polyline"] for entry in geometry["routes"]] == [first, other]
    assert "route_map" not in restored.payload
    assert "polyline" not in restored.payload
    import json
    from html.parser import HTMLParser

    class Marker(HTMLParser):
        payload = None

        def handle_starttag(self, tag, attrs):
            if tag == "div":
                wire = dict(attrs).get("data-route-map")
                if wire:
                    self.payload = json.loads(wire)

    marker = Marker()
    marker.feed(RouteCard().render(card_payload(restored), RenderContext(language="fr")))
    assert marker.payload == geometry


@pytest.mark.parametrize("value", [None, {}, True, ["PRIVATE_TREE"]])
def test_malformed_optional_provider_groups_keep_the_computed_route(value):
    raw = route_response(1)
    raw["routes"][0].update({"polyline": value, "travelAdvisory": value, "legs": value})
    output = formatted(raw)
    assert output["success"] is True


@pytest.mark.parametrize("value", [None, {}, True, ["PRIVATE_TREE"]])
def test_transit_alternative_scoring_handles_malformed_optional_groups(value):
    raw = route_response(1)
    raw["routes"][0]["legs"] = value
    raw["routes"].append({"distanceMeters": 1, "duration": "1s", "legs": []})
    assert _format_route_response(raw, "A", "B", TravelMode.TRANSIT, "en")["success"] is True


def test_all_estimated_toll_currencies_and_zero_remain_reachable():
    raw = route_response(1)
    raw["routes"][0]["travelAdvisory"] = {
        "tollInfo": {
            "estimatedPrice": [
                {"currencyCode": "EUR", "units": "2", "nanos": 500000000},
                {"currencyCode": "CHF", "units": "0", "nanos": 0},
            ]
        }
    }
    output = formatted(raw)
    _, item = _create_route_registry_item(output, "A", "B", TravelMode.DRIVE)
    markup = RouteCard().render(card_payload(item), RenderContext(language="en"))
    assert "2.50 EUR" in markup
    assert "0.00 CHF" in markup
    assert markup.count("2.50 EUR") == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("duration", {}),
        ("duration", "NaNs"),
        ("duration", "-1s"),
        ("distanceMeters", True),
        ("distanceMeters", "bad"),
        ("distanceMeters", -1),
    ],
)
def test_invalid_computed_measurements_return_a_recoverable_failure(field, value):
    raw = route_response(1)
    raw["routes"][0][field] = value
    assert formatted(raw)["success"] is False


def test_large_waypoint_route_opens_each_leg_without_silently_dropping_stops():
    from bs4 import BeautifulSoup

    output = _format_route_response(
        route_response(1),
        "Start",
        "End",
        TravelMode.DRIVE,
        "en",
        waypoints=[f"Stop {i}" for i in range(7)],
        avoid_tolls=True,
    )
    _, item = _create_route_registry_item(output, "Start", "End", TravelMode.DRIVE)
    assert item.payload["maps_url"] == ""
    markup = BeautifulSoup(
        RouteCard().render(card_payload(item), RenderContext(language="en")), "html.parser"
    )
    links = markup.select(".lia-route-links a")
    assert len(links) == 8
    endpoints = [parse_qs(urlsplit(link["href"]).query) for link in links]
    assert endpoints[0]["origin"] == ["Start"]
    assert endpoints[-1]["destination"] == ["End"]
    assert all(endpoint["avoid"] == ["tolls"] for endpoint in endpoints)


def test_universal_route_link_retains_mode_avoidances_and_refuses_oversized_urls():
    from src.domains.agents.display.urls import build_route_url

    url = build_route_url("A", "B", "TWO_WHEELER", avoid_highways=True, avoid_ferries=True)
    assert parse_qs(urlsplit(url).query)["travelmode"] == ["two-wheeler"]
    assert parse_qs(urlsplit(url).query)["avoid"] == ["highways,ferries"]
    assert build_route_url("A", "é" * 1000, "DRIVE") == ""


@pytest.mark.parametrize("latitude", [None, True, "wrong", 91, float("inf")])
def test_malformed_archived_leg_coordinates_do_not_offer_a_misleading_map(latitude):
    from src.domains.agents.display.components.route_journey import render_route_details

    markup = render_route_details(
        {
            "legs": [
                {
                    "start_location": {"latitude": latitude, "longitude": 0},
                    "end_location": {"latitude": 0, "longitude": 0},
                }
            ]
        },
        RenderContext(language="en"),
    )
    assert "maps/dir" not in markup


def route_response(steps=20):
    return {
        "routes": [
            {
                "distanceMeters": 1234,
                "duration": "125s",
                "legs": [
                    {
                        "distanceMeters": 1234,
                        "duration": "125s",
                        "steps": [
                            {
                                "navigationInstruction": {
                                    "instructions": f"INSTRUCTION_{index}",
                                    "maneuver": "TURN_LEFT",
                                },
                                "distanceMeters": 0 if index == 0 else 50,
                                "staticDuration": "3s",
                            }
                            for index in range(steps)
                        ],
                    }
                ],
            }
        ]
    }


def formatted(raw):
    return _format_route_response(
        raw,
        "A & B",
        "C ? D",
        TravelMode.DRIVE,
        "en",
        user_timezone="UTC",
        departure_time="2026-10-03T10:00:00Z",
    )


def test_all_supplied_steps_survive_registry_but_model_preview_stays_bounded(monkeypatch):
    monkeypatch.setattr(settings, "routes_max_steps", 3)
    output = formatted(route_response())
    _, item = _create_route_registry_item(output, "A & B", "C ? D", TravelMode.DRIVE)
    restored = RegistryItem.model_validate_json(item.model_dump_json())
    assert len(restored.payload["steps"]) <= 3
    assert len(card_payload(restored)["steps"]) == 20
    assert restored.payload["distance_meters"] == 1234
    assert "_display_only" not in output["data"]["route"]
    markup = RouteCard().render(card_payload(restored), RenderContext(language="en"))
    assert "INSTRUCTION_19" in markup
    assert "0 m" in markup


def test_maps_link_uses_the_supported_mode_and_encoded_endpoint_values():
    params = parse_qs(urlsplit(formatted(route_response())["data"]["route"]["maps_url"]).query)
    assert params["travelmode"] == ["driving"]
    assert params["origin"] == ["A & B"]
    assert params["destination"] == ["C ? D"]


def test_eta_keeps_supplied_seconds_instead_of_rounding_the_journey_down():
    route = formatted(route_response())["data"]["route"]
    assert route["eta"].endswith("10:02:05+00:00")


def test_alternatives_and_leg_measurements_remain_reachable():
    raw = route_response(1)
    raw["routes"].append({"distanceMeters": 999, "duration": "180s", "legs": []})
    output = formatted(raw)
    _, item = _create_route_registry_item(output, "A", "B", TravelMode.DRIVE)
    data = card_payload(item)
    assert data["legs"][0]["duration_seconds"] == 125
    assert data["alternatives"][0]["distance_meters"] == 999
    assert len(data["alternatives"]) == 1


def test_request_options_and_all_waypoints_survive_the_real_registry():
    output = _format_route_response(
        route_response(1),
        "A",
        "B",
        TravelMode.DRIVE,
        "en",
        waypoints=[f"Stop {i}" for i in range(7)],
        avoid_tolls=True,
        avoid_highways=True,
        avoid_ferries=True,
    )
    _, item = _create_route_registry_item(output, "A", "B", TravelMode.DRIVE)
    data = card_payload(item)
    assert data["avoid_tolls"] and data["avoid_highways"] and data["avoid_ferries"]
    assert data["waypoints"][-1] == "Stop 6"
    markup = RouteCard().render(data, RenderContext(language="en"))
    assert "Stop 6" in markup


def test_returned_optimized_waypoint_order_is_displayed_without_guessing():
    raw = route_response(1)
    raw["routes"][0]["optimizedIntermediateWaypointIndex"] = [1, 0]
    output = _format_route_response(
        raw, "A", "B", TravelMode.DRIVE, "en", waypoints=["First", "Second"]
    )
    assert output["data"]["route"]["waypoints"] == ["Second", "First"]


def test_leg_coordinates_provide_a_local_map_link_even_at_the_equator():
    raw = route_response(1)
    raw["routes"][0]["legs"][0].update(
        {
            "startLocation": {"latLng": {"latitude": 0, "longitude": 0}},
            "endLocation": {"latLng": {"latitude": 1, "longitude": 2}},
        }
    )
    output = formatted(raw)
    _, item = _create_route_registry_item(output, "A", "B", TravelMode.DRIVE)
    markup = RouteCard().render(card_payload(item), RenderContext())
    assert "origin=0.0%2C0.0" in markup
    assert "destination=1.0%2C2.0" in markup
    assert "start_location" not in item.payload


def test_walk_condensation_never_invents_missing_distance(monkeypatch):
    monkeypatch.setattr(settings, "routes_max_steps", 1)
    raw = route_response(3)
    for step in raw["routes"][0]["legs"][0]["steps"]:
        step["travelMode"] = "WALK"
        step.pop("distanceMeters")
    output = _format_route_response(raw, "A", "B", TravelMode.WALK, "en")
    route = output["data"]["route"]
    assert route["steps"][0]["distance_meters"] is None
    assert route["steps_total"] == 3
    assert route["steps_preview_truncated"] is True


@pytest.mark.parametrize("value", [None, {}, True, float("nan"), ["PRIVATE_TREE"]])
def test_bad_optional_route_fields_do_not_break_an_existing_card(value):
    markup = RouteCard().render(
        {
            "origin": "A",
            "destination": "KEPT_ROUTE",
            "travel_mode": value,
            "distance_km": value,
            "duration_minutes": value,
            "steps": [value],
            "toll_info": value,
            "maps_url": value,
            "static_map_url": value,
            "traffic_conditions": value,
            "waypoints": [value],
            "duration_formatted": value,
        },
        RenderContext(),
    )
    assert "KEPT_ROUTE" in markup
    assert "PRIVATE_TREE" not in markup
