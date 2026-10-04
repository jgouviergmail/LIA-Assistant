"""Exact source geometry is bounded, display-only and keeps provider identities."""

import copy
import json

import pytest

from src.domains.agents.tools.route_map_projection import route_map_data
from src.domains.agents.utils.polyline import encode_polyline


def route(points=None, duration="0s", distance=0):
    return {
        "polyline": {"encodedPolyline": encode_polyline(points or [(0, 0), (0, 0)])},
        "duration": duration,
        "distanceMeters": distance,
    }


def test_principal_outside_first_slot_preserves_exact_identity_and_source():
    routes = [route([(0, 179.9), (0, -179.9)], "60s", 150), route()]
    before = copy.deepcopy(routes)
    result = route_map_data(routes, routes[1])
    assert result["primary_id"] == "route-1"
    assert [item["id"] for item in result["routes"]] == ["route-0", "route-1"]
    assert result["routes"][0]["polyline"] == routes[0]["polyline"]["encodedPolyline"]
    assert result["routes"][1]["duration_seconds"] == 0
    assert result["routes"][1]["distance_meters"] == 0
    assert json.loads(json.dumps(result)) == result
    assert routes == before


@pytest.mark.parametrize(
    "bad",
    ["_", "~~", "<script>", "a" * 100001, encode_polyline([(91, 0), (0, 0)])],
    ids=["partial", "unterminated", "html", "oversized", "outside-earth"],
)
def test_invalid_primary_refuses_map_without_inventing_geometry(bad):
    selected = route()
    selected["polyline"]["encodedPolyline"] = bad
    assert route_map_data([selected], selected) is None


def test_malformed_alternative_does_not_poison_primary_and_states_omission():
    selected = route()
    result = route_map_data([None, selected, {"polyline": 7}], selected)
    assert result["primary_id"] == "route-1"
    assert len(result["routes"]) == 1
    assert result["omitted_count"] == 2


def test_equal_route_is_not_mistaken_for_selected_identity():
    selected = route()
    assert route_map_data([copy.deepcopy(selected)], selected) is None


def test_source_family_over_budget_refuses_interactive_map_whole():
    routes = [route() for _ in range(9)]
    assert route_map_data(routes, routes[8]) is None
