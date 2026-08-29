"""
Tests for Google Places tools.

LOT 10: Tests for Google Places location search integration.

Updated for ConnectorTool architecture that retrieves user-specific
OAuth credentials from the database via ToolDependencies.

Updated for UnifiedToolOutput format with Data Registry support.
Places tools use uses_global_api_key=True: the connector check goes through
is_connector_active (no OAuth credentials fetched).
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langgraph.prebuilt.tool_node import ToolRuntime

from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.connectors.schemas import ConnectorCredentials
from tests.helpers.runtime_context import make_tool_runtime


def create_mock_oauth_dependencies(
    credentials: ConnectorCredentials | None = None,
) -> MagicMock:
    """Create a mock ToolDependencies for connector tools.

    Args:
        credentials: When None, simulates a disabled connector
            (is_connector_active -> False for global-API-key tools,
            get_connector_credentials -> None for OAuth tools).
    """
    mock_deps = MagicMock()

    mock_connector_service = MagicMock()
    mock_connector_service.get_connector_credentials = AsyncMock(return_value=credentials)
    # Global-API-key tools (Places) check activation instead of credentials
    mock_connector_service.is_connector_active = AsyncMock(return_value=credentials is not None)
    mock_deps.get_connector_service = AsyncMock(return_value=mock_connector_service)

    # Mock get_or_create_client to return a mock client
    # The factory will be called by execute() to get the client
    mock_deps.get_or_create_client = AsyncMock()

    # Mock db property
    mock_deps.db = MagicMock()

    return mock_deps


@pytest.fixture(autouse=True)
def stub_user_context_helpers():
    """Stub the runtime/location helpers that hit the database or the store.

    get_user_language_safe (runtime_helpers) and the location sources
    (location_resolution: home, last-known, browser) open real DB sessions;
    without this stub each test spends seconds in asyncpg connection retries.
    Any NEW database-touching source added to location_resolution must be
    stubbed here too.
    """
    with (
        patch(
            "src.domains.agents.tools.runtime_helpers.get_user_language_safe",
            new=AsyncMock(return_value="en"),
        ),
        patch(
            "src.domains.agents.tools.location_resolution.get_user_home_location",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.domains.agents.tools.location_resolution.get_user_last_known_location",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.domains.agents.tools.location_resolution.get_browser_geolocation",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.domains.agents.tools.runtime_helpers.get_original_user_message",
            new=MagicMock(return_value=""),  # sync helper (reads state)
        ),
    ):
        yield


def create_mock_runtime(user_id: str) -> ToolRuntime:
    """Create a REAL ToolRuntime with mocked store/writer.

    ToolRuntime is a dataclass whose ``tools`` field only exists on instances
    (default factory), so a ``create_autospec`` mock rejects it when LangChain
    serializes the runtime during args validation.
    """
    mock_store = MagicMock()
    mock_store.get = MagicMock(return_value=None)
    mock_store.put = MagicMock()
    mock_store.aget = AsyncMock(return_value=None)
    mock_store.aput = AsyncMock()

    # ADR-231: identity in the typed context, LangGraph plumbing in the bag.
    return make_tool_runtime(
        user_id=user_id,
        configurable={"thread_id": f"test_thread_{user_id[:8]}"},
        store=mock_store,
        state={},
        tool_call_id="test_call_id",
    )


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

            # Verify UnifiedToolOutput format (Data Registry mode).
            # The LLM summary is a compact registry reference; the place data
            # itself travels through registry_updates.
            assert isinstance(result, UnifiedToolOutput)
            assert result.success is True
            assert "1 place(s)" in result.summary_for_llm
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

            # Verify UnifiedToolOutput format (Data Registry mode)
            assert isinstance(result, UnifiedToolOutput)
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

            # Verify UnifiedToolOutput format (Data Registry mode)
            assert isinstance(result, UnifiedToolOutput)
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

            # Exceptions come back as a serialized UnifiedToolOutput with
            # the ToolErrorCode taxonomy (never a raw traceback)
            data = json.loads(result)
            assert data["success"] is False
            assert data["error_code"] == "INTERNAL_ERROR"

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

            assert isinstance(result, UnifiedToolOutput)
            assert result.success is False
            assert result.error_code == "connector_not_activated"
            assert "places" in result.message.lower()


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

            # Verify UnifiedToolOutput format (Data Registry mode)
            assert isinstance(result, UnifiedToolOutput)
            assert result.success is True
            assert "1 place(s)" in result.summary_for_llm
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

            assert isinstance(result, UnifiedToolOutput)
            assert result.success is False
            assert result.error_code == "connector_not_activated"
            assert "places" in result.message.lower()


class TestListModeNoSearchCriteria:
    """get_places_tool() with no criteria must not fake an empty success (F033).

    The list branch previously returned success=True with an empty list and a
    "requires specific implementation" message — a fake success that made the LLM
    report "no places found". The Places API needs a query/type/location/id, so
    the honest outcome is an explicit business error.
    """

    @pytest.mark.asyncio
    async def test_execute_api_call_returns_business_error(self):
        from src.domains.agents.tools.places_tools import ListPlacesTool

        tool = ListPlacesTool()
        tool.runtime = create_mock_runtime(str(uuid4()))

        result = await tool.execute_api_call(client=MagicMock(), user_id=uuid4())

        assert result["success"] is False
        assert result["error"] == "search_criteria_required"
        assert result["message"]  # localized, non-empty

    @pytest.mark.asyncio
    async def test_format_registry_response_surfaces_failure(self):
        from src.domains.agents.tools.places_tools import ListPlacesTool

        tool = ListPlacesTool()
        tool.runtime = create_mock_runtime(str(uuid4()))

        result = await tool.execute_api_call(client=MagicMock(), user_id=uuid4())
        output = tool.format_registry_response(result)

        assert isinstance(output, UnifiedToolOutput)
        assert output.success is False
        assert output.error_code == "search_criteria_required"
