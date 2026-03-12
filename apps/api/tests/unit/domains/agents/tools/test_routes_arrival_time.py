"""
Unit tests for routes_tools.py arrival_time functionality.

Tests the arrival-based route calculation feature:
- suggested_departure_time calculation
- target_arrival_time formatting
- is_arrival_based flag
- Mutual exclusivity of departure_time and arrival_time
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.domains.connectors.clients.google_routes_client import TravelMode


class TestFormatRouteResponseArrivalBased:
    """Tests for _format_route_response with arrival_time."""

    @pytest.fixture
    def mock_route_data(self):
        """Sample Google Routes API response."""
        return {
            "routes": [
                {
                    "duration": "5400s",  # 90 minutes
                    "distanceMeters": 50000,  # 50 km
                    "polyline": {"encodedPolyline": "encoded_polyline_data"},
                    "legs": [],
                }
            ]
        }

    def test_arrival_based_calculates_suggested_departure(self, mock_route_data):
        """Test that arrival_time calculates correct suggested_departure_time."""
        from src.domains.agents.tools.routes_tools import _format_route_response

        # Arrival at 14:00, duration 90 min → departure should be 12:30
        result = _format_route_response(
            route_data=mock_route_data,
            origin_display="Paris",
            destination_display="Lyon",
            travel_mode=TravelMode.DRIVE,
            language="fr",
            user_timezone="Europe/Paris",
            departure_time=None,
            arrival_time_target="2026-01-20T14:00:00+01:00",
            is_arrival_based=True,
        )

        assert result["success"] is True
        route = result["data"]["route"]

        # Check arrival-based fields are set
        assert route["is_arrival_based"] is True
        assert route["target_arrival_time"] is not None
        # Date is included when not today (20/01 14:00)
        assert "14:00" in route["target_arrival_formatted"]
        assert route["suggested_departure_time"] is not None
        assert "12:30" in route["suggested_departure_formatted"]

        # ETA should contain the target arrival time
        assert "14:00" in route["eta_formatted"]

    def test_non_arrival_based_route_has_no_suggested_departure(self, mock_route_data):
        """Test that regular routes don't have suggested_departure_time."""
        from src.domains.agents.tools.routes_tools import _format_route_response

        result = _format_route_response(
            route_data=mock_route_data,
            origin_display="Paris",
            destination_display="Lyon",
            travel_mode=TravelMode.DRIVE,
            language="fr",
            user_timezone="Europe/Paris",
            departure_time="2026-01-20T10:00:00+01:00",
            arrival_time_target=None,
            is_arrival_based=False,
        )

        assert result["success"] is True
        route = result["data"]["route"]

        # Check arrival-based fields are NOT set
        assert route["is_arrival_based"] is False
        assert route["target_arrival_time"] is None
        assert route["suggested_departure_time"] is None

    def test_arrival_based_handles_tomorrow_date(self, mock_route_data):
        """Test that arrival_time handles tomorrow correctly."""
        from src.domains.agents.tools.routes_tools import _format_route_response

        # Use a time that will be tomorrow
        tz = ZoneInfo("Europe/Paris")
        now = datetime.now(tz)
        tomorrow_14h = now.replace(hour=14, minute=0, second=0, microsecond=0)
        # Add a day if it's already past 14h today
        if now.hour >= 14:
            from datetime import timedelta

            tomorrow_14h = tomorrow_14h + timedelta(days=1)
        else:
            from datetime import timedelta

            tomorrow_14h = tomorrow_14h + timedelta(days=1)

        result = _format_route_response(
            route_data=mock_route_data,
            origin_display="Paris",
            destination_display="Lyon",
            travel_mode=TravelMode.DRIVE,
            language="fr",
            user_timezone="Europe/Paris",
            departure_time=None,
            arrival_time_target=tomorrow_14h.isoformat(),
            is_arrival_based=True,
        )

        assert result["success"] is True
        route = result["data"]["route"]
        assert route["is_arrival_based"] is True
        # Should include "demain" in formatted strings
        assert (
            "demain" in route["target_arrival_formatted"].lower()
            or "14:00" in route["target_arrival_formatted"]
        )

    def test_arrival_time_with_explicit_offset(self, mock_route_data):
        """Test that arrival times with explicit offset are processed correctly.

        Note: UTC-to-local conversion is done in get_route_tool BEFORE calling
        _format_route_response. This test verifies _format_route_response handles
        times that already have the correct offset.
        """
        from src.domains.agents.tools.routes_tools import _format_route_response

        # Time with explicit Paris offset (already converted by get_route_tool)
        result = _format_route_response(
            route_data=mock_route_data,
            origin_display="Paris",
            destination_display="Bastille",
            travel_mode=TravelMode.TRANSIT,
            language="fr",
            user_timezone="Europe/Paris",
            departure_time=None,
            arrival_time_target="2026-01-20T21:00:00+01:00",  # Already has correct offset
            is_arrival_based=True,
        )

        assert result["success"] is True
        route = result["data"]["route"]

        # Should be 21:00 as specified
        assert route["is_arrival_based"] is True
        assert "21:00" in route["target_arrival_formatted"]
        # Suggested departure should be 21:00 - 90min = 19:30
        assert "19:30" in route["suggested_departure_formatted"]


class TestRoutesCacheArrivalTime:
    """Tests for RoutesCache arrival_time handling."""

    def test_cache_key_differs_for_arrival_vs_departure(self):
        """Test that cache keys are different for arrival_time vs departure_time."""
        from src.infrastructure.cache.routes_cache import RoutesCache

        # Create a mock redis client
        class MockRedis:
            pass

        cache = RoutesCache(MockRedis())

        # Same route, same time, but departure vs arrival
        key_departure = cache._make_route_key(
            origin="Paris",
            destination="Lyon",
            travel_mode="DRIVE",
            departure_time="2026-01-20T14:00:00Z",
            arrival_time=None,
        )

        key_arrival = cache._make_route_key(
            origin="Paris",
            destination="Lyon",
            travel_mode="DRIVE",
            departure_time=None,
            arrival_time="2026-01-20T14:00:00Z",
        )

        # Keys should be different
        assert key_departure != key_arrival

    def test_cache_key_same_for_same_arrival_time(self):
        """Test that cache keys are same for identical arrival_time requests."""
        from src.infrastructure.cache.routes_cache import RoutesCache

        class MockRedis:
            pass

        cache = RoutesCache(MockRedis())

        key1 = cache._make_route_key(
            origin="Paris",
            destination="Lyon",
            travel_mode="TRANSIT",
            departure_time=None,
            arrival_time="2026-01-20T14:00:00Z",
        )

        key2 = cache._make_route_key(
            origin="Paris",
            destination="Lyon",
            travel_mode="TRANSIT",
            departure_time=None,
            arrival_time="2026-01-20T14:30:00Z",  # Same hour, truncated
        )

        # Keys should be same (truncated to hour)
        assert key1 == key2


class TestGoogleRoutesClientArrivalTime:
    """Tests for GoogleRoutesClient arrival_time handling."""

    def test_departure_and_arrival_mutually_exclusive(self):
        """Test that departure_time and arrival_time cannot both be set."""
        from src.domains.connectors.clients.google_routes_client import GoogleRoutesClient

        client = GoogleRoutesClient()

        with pytest.raises(ValueError, match="mutually exclusive"):
            import asyncio

            asyncio.get_event_loop().run_until_complete(
                client.compute_route(
                    origin="Paris",
                    destination="Lyon",
                    departure_time="2026-01-20T10:00:00Z",
                    arrival_time="2026-01-20T14:00:00Z",
                )
            )


class TestRouteItemSchema:
    """Tests for RouteItem schema with arrival-based fields."""

    def test_route_item_has_arrival_based_fields(self):
        """Test that RouteItem schema includes arrival-based fields."""
        from src.domains.agents.tools.routes_tools import RouteItem

        item = RouteItem(
            origin="Paris",
            destination="Lyon",
            travel_mode="DRIVE",
            is_arrival_based=True,
            target_arrival_time="2026-01-20T14:00:00+01:00",
            target_arrival_formatted="14:00",
            suggested_departure_time="2026-01-20T12:30:00+01:00",
            suggested_departure_formatted="12:30",
        )

        assert item.is_arrival_based is True
        assert item.target_arrival_time == "2026-01-20T14:00:00+01:00"
        assert item.suggested_departure_time == "2026-01-20T12:30:00+01:00"

    def test_route_item_defaults_to_non_arrival_based(self):
        """Test that RouteItem defaults is_arrival_based to False."""
        from src.domains.agents.tools.routes_tools import RouteItem

        item = RouteItem(
            origin="Paris",
            destination="Lyon",
        )

        assert item.is_arrival_based is False
        assert item.target_arrival_time is None
        assert item.suggested_departure_time is None


class TestI18nArrivalMessages:
    """Tests for i18n messages related to arrival-based routing."""

    def test_get_to_arrive_by_french(self):
        """Test French message for arrival-based route."""
        from src.core.i18n_v3 import V3Messages

        result = V3Messages.get_to_arrive_by("fr", "14:00", "12:30")
        assert result == "Pour arriver à 14:00, partez à 12:30"

    def test_get_to_arrive_by_english(self):
        """Test English message for arrival-based route."""
        from src.core.i18n_v3 import V3Messages

        result = V3Messages.get_to_arrive_by("en", "2:00 PM", "12:30 PM")
        assert result == "To arrive by 2:00 PM, leave at 12:30 PM"

    def test_get_suggested_departure_labels(self):
        """Test suggested departure labels in different languages."""
        from src.core.i18n_v3 import V3Messages

        assert V3Messages.get_suggested_departure("fr") == "Départ conseillé"
        assert V3Messages.get_suggested_departure("en") == "Suggested departure"
        assert V3Messages.get_suggested_departure("es") == "Salida sugerida"
