"""Route clocks survive production formatting, registry storage and card rendering."""

from datetime import UTC, datetime

import pytest
from bs4 import BeautifulSoup

from src.core.time_parsing import parse_rfc3339
from src.domains.agents.data_registry.card_payload import card_payload
from src.domains.agents.data_registry.models import RegistryItem
from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.route_card import RouteCard
from src.domains.agents.tools.routes_tools import (
    RouteItem,
    _create_route_registry_item,
    _format_route_response,
)
from src.domains.connectors.clients.google_routes_client import TravelMode

pytestmark = pytest.mark.unit


def _route(
    departure: str | None = "2026-11-20T09:15:00Z",
    *,
    arrival: str | None = None,
    arrival_based: bool = False,
    duration: str = "3600s",
    raw: dict[str, object] | None = None,
) -> dict[str, object]:
    """Exercise the real provider projection with explicit instants by default."""
    result = _format_route_response(
        raw or {"routes": [{"duration": duration, "distanceMeters": 1000}]},
        "Start",
        "End",
        TravelMode.TRANSIT if raw else TravelMode.DRIVE,
        "fr",
        "Europe/Paris",
        departure,
        arrival_time_target=arrival,
        is_arrival_based=arrival_based,
    )
    assert result["success"] is True
    route = result["data"]["route"]
    assert isinstance(route, dict)
    return route


def _card(route: dict[str, object], *, timezone: str = "Europe/Paris") -> BeautifulSoup:
    """Read the same serialized registry boundary as an archived response."""
    _, item = _create_route_registry_item(
        {"data": {"route": route}}, "Start", "End", TravelMode.DRIVE
    )
    restored = RegistryItem.model_validate_json(item.model_dump_json())
    return BeautifulSoup(
        RouteCard().render(card_payload(restored), RenderContext(language="fr", timezone=timezone)),
        "html.parser",
    )


def test_normal_departure_reaches_context_and_card_beside_arrival() -> None:
    route = _route()
    assert route.get("departure_time") == "2026-11-20T10:15:00+01:00"
    assert route["eta"] == "2026-11-20T11:15:00+01:00"
    typed = RouteItem.model_validate(route).model_dump()
    assert typed.get("departure_time") == route["departure_time"]
    assert typed.get("departure_formatted") == route["departure_formatted"]
    text = _card(route).get_text(" ", strip=True)
    assert "Départ 20/11 10:15" in text
    assert "Arrivée 20/11 11:15" in text
    assert "Départ conseillé" not in text


@pytest.mark.parametrize("duration", ["0s", "1800s"])
def test_immediate_route_retains_the_instant_used_for_its_eta(duration: str) -> None:
    before = datetime.now(UTC)
    route = _route(None, duration=duration)
    after = datetime.now(UTC)
    departure = parse_rfc3339(route.get("departure_time"))
    eta = parse_rfc3339(route.get("eta"))
    assert departure is not None and eta is not None
    assert before <= departure <= after
    assert (eta.astimezone(UTC) - departure.astimezone(UTC)).total_seconds() == int(duration[:-1])


@pytest.mark.parametrize(
    "departure,expected",
    [
        ("2026-03-29T01:30:00+01:00", "2026-03-29T04:30:00+02:00"),
        ("2026-10-25T01:30:00+02:00", "2026-10-25T02:30:00+01:00"),
    ],
)
def test_eta_adds_elapsed_seconds_across_daylight_saving(departure: str, expected: str) -> None:
    assert _route(departure, duration="7200s")["eta"] == expected


@pytest.mark.parametrize(
    "arrival,expected",
    [
        ("2026-03-29T04:30:00+02:00", "2026-03-29T01:30:00+01:00"),
        ("2026-10-25T03:30:00+01:00", "2026-10-25T02:30:00+02:00"),
    ],
)
def test_arrival_target_subtracts_elapsed_seconds_across_daylight_saving(
    arrival: str, expected: str
) -> None:
    route = _route(None, arrival=arrival, arrival_based=True, duration="7200s")
    assert route["suggested_departure_time"] == expected
    assert route["target_arrival_time"] == arrival
    assert "Départ conseillé" in _card(route).get_text(" ", strip=True)


def test_zero_duration_arrival_route_keeps_both_identical_clocks() -> None:
    route = _route(None, arrival="2026-11-20T09:15:00Z", arrival_based=True, duration="0s")
    assert route["suggested_departure_time"] == route["eta"] == "2026-11-20T10:15:00+01:00"
    text = _card(route).get_text(" ", strip=True)
    assert "Départ conseillé" in text and "Arrivée" in text


@pytest.mark.parametrize("invalid", ["wrong", "2026-11-20", "2026-11-20T09:15:00", ""])
@pytest.mark.parametrize("arrival_based", [False, True])
def test_malformed_explicit_clock_never_falls_back_to_now(
    invalid: str, arrival_based: bool
) -> None:
    route = _route(
        None if arrival_based else invalid,
        arrival=invalid if arrival_based else None,
        arrival_based=arrival_based,
    )
    assert route.get("departure_time") is None
    assert route["eta"] is None
    assert route["suggested_departure_time"] is None


def test_archived_arrival_without_departure_does_not_reconstruct_a_clock() -> None:
    markup = _card({"destination": "End", "duration_minutes": 60, "eta_formatted": "11:15"})
    clocks = " ".join(chip.get_text(" ", strip=True) for chip in markup.select(".lia-chip"))
    assert "Arrivée 11:15" in clocks
    assert "Départ" not in clocks


def test_transit_stop_clocks_survive_both_primary_and_alternative_projection() -> None:
    step = {
        "travelMode": "TRANSIT",
        "transitDetails": {
            "transitLine": {"nameShort": "R", "vehicle": {"type": "RAIL"}},
            "stopDetails": {
                "departureStop": {"name": "First station"},
                "arrivalStop": {"name": "Last station"},
                "departureTime": "2026-11-20T23:45:00Z",
                "arrivalTime": "2026-11-21T00:25:00Z",
            },
        },
    }
    provider_route = {"duration": "3600s", "distanceMeters": 1000, "legs": [{"steps": [step]}]}
    route = _route(raw={"routes": [provider_route, {**provider_route}]})
    markup = _card(route, timezone="America/New_York")
    details = markup.select(".lia-route-step__detail")
    assert len(details) == 2
    for detail in details:
        text = detail.get_text(" ", strip=True)
        assert "First station" in text and "Last station" in text
        assert "Départ" in text and "18:45" in text
        assert "Arrivée" in text and "19:25" in text


@pytest.mark.parametrize("invalid", [None, {}, True, "wrong", "2026-11-20T09:15:00"])
def test_malformed_transit_clock_does_not_remove_the_stop_or_invent_a_time(invalid: object) -> None:
    markup = _card(
        {
            "destination": "End",
            "steps": [
                {
                    "travel_mode": "TRANSIT",
                    "transit": {"departure_stop": "First station", "departure_time": invalid},
                }
            ],
        }
    )
    detail = markup.select_one(".lia-route-step__detail")
    assert detail is not None
    text = detail.get_text(" ", strip=True)
    assert "First station" in text
    assert "Départ" not in text
