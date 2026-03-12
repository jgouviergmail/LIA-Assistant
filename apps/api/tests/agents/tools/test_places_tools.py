"""
Tests for Google Places tools.

LOT 10: Tests for Google Places location search integration.

Updated for ConnectorTool architecture that retrieves user-specific
OAuth credentials from the database via ToolDependencies.

Updated for StandardToolOutput format with Data Registry support.
"""

import json
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch
from uuid import uuid4

import pytest
from langgraph.prebuilt.tool_node import ToolRuntime

from src.domains.agents.tools.output import StandardToolOutput
from src.domains.connectors.schemas import ConnectorCredentials


def create_mock_oauth_dependencies(
    credentials: ConnectorCredentials | None = None,
) -> MagicMock:
    """Create a mock ToolDependencies for OAuth connectors.

    Args:
        credentials: Credentials to return from get_connector_credentials.
            If None, simulates disabled connector.
    """
    mock_deps = MagicMock()

    # Mock connector service with get_connector_credentials
    mock_connector_service = MagicMock()
    mock_connector_service.get_connector_credentials = AsyncMock(return_value=credentials)
    mock_deps.get_connector_service = AsyncMock(return_value=mock_connector_service)

    # Mock get_or_create_client to return a mock client
    # The factory will be called by execute() to get the client
    mock_deps.get_or_create_client = AsyncMock()

    # Mock db property
    mock_deps.db = MagicMock()

    return mock_deps


def create_mock_runtime(user_id: str) -> ToolRuntime:
    """Create a mock ToolRuntime with configurable user_id."""
    runtime = create_autospec(ToolRuntime, instance=True)
    configurable = {
        "user_id": user_id,
        "thread_id": f"test_thread_{user_id[:8]}",
    }

    runtime.config = {"configurable": configurable}
    mock_store = MagicMock()
    mock_store.get = MagicMock(return_value=None)
    mock_store.put = MagicMock()
    runtime.store = mock_store
    runtime.state = {}
    runtime.context = {}
    runtime.stream_writer = MagicMock()
    runtime.tool_call_id = "test_call_id"
    return runtime


class TestSearchPlacesTool:
    """Tests for search_places_tool with ConnectorTool architecture."""

    @pytest.fixture
    def mock_credentials(self) -> ConnectorCredentials:
        """Create mock OAuth credentials."""
        return ConnectorCredentials(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            expires_at=9999999999,
        )

    @pytest.fixture
    def user_id(self) -> str:
        """Generate test user ID."""
        return str(uuid4())

    @pytest.fixture
    def mock_client(self):
        """Create a mock Places client."""
        client = AsyncMock()
        client.search_text = AsyncMock(
            return_value={
                "places": [
                    {
                        "id": "ChIJLU7jZClu5kcR4PcOy",
                        "displayName": {"text": "Le Jules Verne"},
                        "formattedAddress": "Tour Eiffel, Paris",
                        "location": {"latitude": 48.8584, "longitude": 2.2945},
                        "rating": 4.5,
                        "userRatingCount": 1200,
                        "priceLevel": "PRICE_LEVEL_EXPENSIVE",
                        "types": ["restaurant", "french_restaurant"],
                        "googleMapsUri": "https://maps.google.com/...",
                    },
                ],
                "query": "restaurants Tour Eiffel",
                "total": 1,
            }
        )
        return client

    @pytest.mark.asyncio
    async def test_search_success(self, mock_credentials, user_id, mock_client):
        """Test successful place search."""
        from src.domains.agents.tools.places_tools import _search_places_tool_instance

        mock_deps = create_mock_oauth_dependencies(credentials=mock_credentials)
        # Configure get_or_create_client to return the mock client
        mock_deps.get_or_create_client = AsyncMock(return_value=mock_client)
        runtime = create_mock_runtime(user_id)

        with patch(
            "src.domains.agents.tools.base.get_dependencies",
            return_value=mock_deps,
        ):
            result = await _search_places_tool_instance.execute(
                runtime,
                query="restaurants Tour Eiffel",
            )

            # Verify StandardToolOutput format
            assert isinstance(result, StandardToolOutput)
            assert "Le Jules Verne" in result.summary_for_llm
            assert len(result.registry_updates) == 1
            # Verify registry item
            registry_item = list(result.registry_updates.values())[0]
            assert registry_item.payload["name"] == "Le Jules Verne"
            assert registry_item.payload["rating"] == 4.5

    @pytest.mark.asyncio
    async def test_search_with_type_filter(self, mock_credentials, user_id, mock_client):
        """Test search with place type filter."""
        from src.domains.agents.tools.places_tools import _search_places_tool_instance

        mock_deps = create_mock_oauth_dependencies(credentials=mock_credentials)
        mock_deps.get_or_create_client = AsyncMock(return_value=mock_client)
        runtime = create_mock_runtime(user_id)

        with patch(
            "src.domains.agents.tools.base.get_dependencies",
            return_value=mock_deps,
        ):
            result = await _search_places_tool_instance.execute(
                runtime,
                query="food in Paris",
                place_type="restaurant",
            )

            # Verify StandardToolOutput format
            assert isinstance(result, StandardToolOutput)
            mock_client.search_text.assert_called_once()
            call_args = mock_client.search_text.call_args
            assert call_args.kwargs["include_type"] == "restaurant"

    @pytest.mark.asyncio
    async def test_search_with_open_now(self, mock_credentials, user_id, mock_client):
        """Test search with open_now filter."""
        from src.domains.agents.tools.places_tools import _search_places_tool_instance

        mock_deps = create_mock_oauth_dependencies(credentials=mock_credentials)
        mock_deps.get_or_create_client = AsyncMock(return_value=mock_client)
        runtime = create_mock_runtime(user_id)

        with patch(
            "src.domains.agents.tools.base.get_dependencies",
            return_value=mock_deps,
        ):
            result = await _search_places_tool_instance.execute(
                runtime,
                query="pharmacy",
                open_now=True,
            )

            # Verify StandardToolOutput format
            assert isinstance(result, StandardToolOutput)
            call_args = mock_client.search_text.call_args
            assert call_args.kwargs["open_now"] is True

    @pytest.mark.asyncio
    async def test_search_api_error(self, mock_credentials, user_id):
        """Test handling of API errors."""
        from src.domains.agents.tools.places_tools import _search_places_tool_instance

        mock_client = AsyncMock()
        mock_client.search_text = AsyncMock(side_effect=Exception("API Error"))

        mock_deps = create_mock_oauth_dependencies(credentials=mock_credentials)
        mock_deps.get_or_create_client = AsyncMock(return_value=mock_client)
        runtime = create_mock_runtime(user_id)

        with patch(
            "src.domains.agents.tools.base.get_dependencies",
            return_value=mock_deps,
        ):
            result = await _search_places_tool_instance.execute(
                runtime,
                query="test",
            )

            data = json.loads(result)
            assert data["success"] is False
            assert "error" in data

    @pytest.mark.asyncio
    async def test_search_connector_not_activated(self, user_id):
        """Test handling when connector is not activated."""
        from src.domains.agents.tools.places_tools import _search_places_tool_instance

        # No credentials = connector not activated
        mock_deps = create_mock_oauth_dependencies(credentials=None)
        runtime = create_mock_runtime(user_id)

        with patch(
            "src.domains.agents.tools.base.get_dependencies",
            return_value=mock_deps,
        ):
            result = await _search_places_tool_instance.execute(
                runtime,
                query="Test query",
            )

            data = json.loads(result)
            assert data["error"] == "connector_not_activated"
            assert "google_places" in data["message"].lower() or "places" in data["message"].lower()


class TestGetPlaceDetailsTool:
    """Tests for get_place_details_tool with ConnectorTool architecture."""

    @pytest.fixture
    def mock_credentials(self) -> ConnectorCredentials:
        """Create mock OAuth credentials."""
        return ConnectorCredentials(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            expires_at=9999999999,
        )

    @pytest.fixture
    def user_id(self) -> str:
        """Generate test user ID."""
        return str(uuid4())

    @pytest.fixture
    def mock_client(self):
        """Create a mock Places client."""
        client = AsyncMock()
        client.get_place_details = AsyncMock(
            return_value={
                "id": "ChIJLU7jZClu5kcR4PcOy",
                "displayName": {"text": "Le Jules Verne"},
                "formattedAddress": "Tour Eiffel, Av Gustave Eiffel, Paris",
                "location": {"latitude": 48.8584, "longitude": 2.2945},
                "rating": 4.5,
                "userRatingCount": 1200,
                "priceLevel": "PRICE_LEVEL_EXPENSIVE",
                "nationalPhoneNumber": "01 45 55 61 44",
                "websiteUri": "https://www.lejulesverne-paris.com",
                "regularOpeningHours": {
                    "weekdayDescriptions": [
                        "Monday: 12:00-2:00 PM, 7:00-11:00 PM",
                    ],
                },
                "currentOpeningHours": {"openNow": True},
                "editorialSummary": {"text": "Upscale French restaurant in the Eiffel Tower"},
                "reviews": [
                    {
                        "rating": 5,
                        "text": {"text": "Amazing view and food!"},
                        "relativePublishTimeDescription": "2 months ago",
                    },
                ],
                "types": ["restaurant"],
                "googleMapsUri": "https://maps.google.com/...",
            }
        )
        return client

    @pytest.mark.asyncio
    async def test_get_details_success(self, mock_credentials, user_id, mock_client):
        """Test successful place details retrieval."""
        from src.domains.agents.tools.places_tools import _get_place_details_tool_instance

        mock_deps = create_mock_oauth_dependencies(credentials=mock_credentials)
        mock_deps.get_or_create_client = AsyncMock(return_value=mock_client)
        runtime = create_mock_runtime(user_id)

        with patch(
            "src.domains.agents.tools.base.get_dependencies",
            return_value=mock_deps,
        ):
            result = await _get_place_details_tool_instance.execute(
                runtime,
                place_id="ChIJLU7jZClu5kcR4PcOy",
            )

            # Verify StandardToolOutput format
            assert isinstance(result, StandardToolOutput)
            assert "Le Jules Verne" in result.summary_for_llm
            assert "01 45 55 61 44" in result.summary_for_llm
            assert len(result.registry_updates) == 1
            # Verify registry item
            registry_item = list(result.registry_updates.values())[0]
            assert registry_item.payload["name"] == "Le Jules Verne"
            assert registry_item.payload["rating"] == 4.5
            assert registry_item.payload["phone"] == "01 45 55 61 44"
            assert registry_item.payload["website"] == "https://www.lejulesverne-paris.com"
            assert registry_item.payload["open_now"] is True

    @pytest.mark.asyncio
    async def test_get_details_connector_not_activated(self, user_id):
        """Test handling when connector is not activated."""
        from src.domains.agents.tools.places_tools import _get_place_details_tool_instance

        # No credentials = connector not activated
        mock_deps = create_mock_oauth_dependencies(credentials=None)
        runtime = create_mock_runtime(user_id)

        with patch(
            "src.domains.agents.tools.base.get_dependencies",
            return_value=mock_deps,
        ):
            result = await _get_place_details_tool_instance.execute(
                runtime,
                place_id="ChIJLU7jZClu5kcR4PcOy",
            )

            data = json.loads(result)
            assert data["error"] == "connector_not_activated"
            assert "google_places" in data["message"].lower() or "places" in data["message"].lower()


class TestApplyDistanceRangeFilter:
    """Tests for _apply_distance_range_filter helper function."""

    def test_no_filter_when_min_radius_none(self):
        """Test that places are returned unchanged when min_radius is None."""
        from src.domains.agents.tools.places_tools import _apply_distance_range_filter

        places = [
            {"name": "Place A", "distance_km": 1.0},
            {"name": "Place B", "distance_km": 5.0},
            {"name": "Place C", "distance_km": 10.0},
        ]

        result = _apply_distance_range_filter(places, None, 50000, 10)

        assert result == places
        assert len(result) == 3

    def test_filter_within_range(self):
        """Test filtering places within distance range."""
        from src.domains.agents.tools.places_tools import _apply_distance_range_filter

        places = [
            {"name": "Too Close", "distance_km": 5.0},
            {"name": "In Range 1", "distance_km": 45.0},
            {"name": "In Range 2", "distance_km": 50.0},
            {"name": "In Range 3", "distance_km": 55.0},
            {"name": "Too Far", "distance_km": 70.0},
        ]

        # Filter: 40km <= distance <= 60km
        result = _apply_distance_range_filter(places, 40000, 60000, 10)

        assert len(result) == 3
        assert all(p["name"].startswith("In Range") for p in result)

    def test_filter_respects_max_results(self):
        """Test that max_results limit is applied after filtering."""
        from src.domains.agents.tools.places_tools import _apply_distance_range_filter

        places = [{"name": f"Place {i}", "distance_km": float(45 + i)} for i in range(10)]

        # Filter: 40km <= distance <= 100km, max 3 results
        result = _apply_distance_range_filter(places, 40000, 100000, 3)

        assert len(result) == 3

    def test_filter_sorts_by_distance(self):
        """Test that results are sorted by distance (closest first)."""
        from src.domains.agents.tools.places_tools import _apply_distance_range_filter

        places = [
            {"name": "Far", "distance_km": 55.0},
            {"name": "Close", "distance_km": 45.0},
            {"name": "Medium", "distance_km": 50.0},
        ]

        # Filter: 40km <= distance <= 60km
        result = _apply_distance_range_filter(places, 40000, 60000, 10)

        assert len(result) == 3
        assert result[0]["name"] == "Close"
        assert result[1]["name"] == "Medium"
        assert result[2]["name"] == "Far"

    def test_filter_handles_missing_distance(self):
        """Test that places without distance_km are excluded."""
        from src.domains.agents.tools.places_tools import _apply_distance_range_filter

        places = [
            {"name": "Has Distance", "distance_km": 50.0},
            {"name": "No Distance"},
            {"name": "Null Distance", "distance_km": None},
        ]

        # Filter: 40km <= distance <= 60km
        result = _apply_distance_range_filter(places, 40000, 60000, 10)

        assert len(result) == 1
        assert result[0]["name"] == "Has Distance"

    def test_filter_empty_input(self):
        """Test filtering empty list returns empty list."""
        from src.domains.agents.tools.places_tools import _apply_distance_range_filter

        result = _apply_distance_range_filter([], 40000, 60000, 10)

        assert result == []

    def test_filter_no_matches(self):
        """Test filtering when no places match the range."""
        from src.domains.agents.tools.places_tools import _apply_distance_range_filter

        places = [
            {"name": "Too Close", "distance_km": 10.0},
            {"name": "Too Far", "distance_km": 100.0},
        ]

        # Filter: 40km <= distance <= 60km
        result = _apply_distance_range_filter(places, 40000, 60000, 10)

        assert result == []
