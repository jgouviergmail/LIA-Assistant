"""
Unit tests for preference resolver with case-insensitive matching.

Tests cover:
- PreferenceNameResolver: Generic resolver with case matching
- GoogleCalendarNameResolver: Calendar-specific resolution
- GoogleTasksListNameResolver: Tasks-specific resolution
- Case-insensitive matching behavior
- Fallback behavior when name not found
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.connectors.preferences.resolver import (
    GoogleCalendarNameResolver,
    GoogleTasksListNameResolver,
    PreferenceNameResolver,
    ResolvedItem,
    resolve_calendar_name,
    resolve_task_list_name,
)


class TestPreferenceNameResolver:
    """Tests for generic PreferenceNameResolver."""

    @pytest.fixture
    def mock_strategy(self):
        """Create a mock strategy for testing."""
        strategy = MagicMock()
        strategy.fetch_items = AsyncMock()
        strategy.get_item_name = MagicMock(side_effect=lambda x: x.get("name", ""))
        strategy.get_item_id = MagicMock(side_effect=lambda x: x.get("id", ""))
        return strategy

    @pytest.fixture
    def mock_client(self):
        """Create a mock client."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_resolve_exact_match(self, mock_client, mock_strategy):
        """Test exact case match returns exact_match=True."""
        # Arrange
        mock_strategy.fetch_items.return_value = [
            {"id": "cal_123", "name": "Famille"},
            {"id": "cal_456", "name": "Work"},
        ]

        # Act
        result = await PreferenceNameResolver.resolve(
            client=mock_client,
            name="Famille",  # Exact case
            strategy=mock_strategy,
        )

        # Assert
        assert result is not None
        assert result.id == "cal_123"
        assert result.name == "Famille"
        assert result.exact_match is True

    @pytest.mark.asyncio
    async def test_resolve_case_insensitive_match(self, mock_client, mock_strategy):
        """Test case-insensitive match returns exact_match=False."""
        # Arrange
        mock_strategy.fetch_items.return_value = [
            {"id": "cal_123", "name": "Famille"},
            {"id": "cal_456", "name": "Work"},
        ]

        # Act - lowercase "famille" should match "Famille"
        result = await PreferenceNameResolver.resolve(
            client=mock_client,
            name="famille",  # Different case
            strategy=mock_strategy,
        )

        # Assert
        assert result is not None
        assert result.id == "cal_123"
        assert result.name == "Famille"
        assert result.exact_match is False

    @pytest.mark.asyncio
    async def test_resolve_case_insensitive_uppercase(self, mock_client, mock_strategy):
        """Test uppercase name matches lowercase calendar."""
        # Arrange
        mock_strategy.fetch_items.return_value = [
            {"id": "cal_123", "name": "famille"},
            {"id": "cal_456", "name": "Work"},
        ]

        # Act
        result = await PreferenceNameResolver.resolve(
            client=mock_client,
            name="FAMILLE",  # Uppercase
            strategy=mock_strategy,
        )

        # Assert
        assert result is not None
        assert result.id == "cal_123"
        assert result.exact_match is False

    @pytest.mark.asyncio
    async def test_resolve_not_found_with_fallback(self, mock_client, mock_strategy):
        """Test fallback is returned when name not found."""
        # Arrange
        mock_strategy.fetch_items.return_value = [
            {"id": "cal_123", "name": "Work"},
        ]

        # Act
        result = await PreferenceNameResolver.resolve(
            client=mock_client,
            name="NonExistent",
            strategy=mock_strategy,
            fallback_id="primary",
        )

        # Assert
        assert result is not None
        assert result.id == "primary"
        assert result.name == ""
        assert result.exact_match is False

    @pytest.mark.asyncio
    async def test_resolve_not_found_no_fallback(self, mock_client, mock_strategy):
        """Test None is returned when name not found and no fallback."""
        # Arrange
        mock_strategy.fetch_items.return_value = [
            {"id": "cal_123", "name": "Work"},
        ]

        # Act
        result = await PreferenceNameResolver.resolve(
            client=mock_client,
            name="NonExistent",
            strategy=mock_strategy,
            fallback_id=None,
        )

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_empty_name_with_fallback(self, mock_client, mock_strategy):
        """Test empty name returns fallback."""
        # Act
        result = await PreferenceNameResolver.resolve(
            client=mock_client,
            name="",
            strategy=mock_strategy,
            fallback_id="primary",
        )

        # Assert
        assert result is not None
        assert result.id == "primary"

    @pytest.mark.asyncio
    async def test_resolve_none_name_with_fallback(self, mock_client, mock_strategy):
        """Test None name returns fallback."""
        # Act - Note: type hint says str, but we test None for robustness
        result = await PreferenceNameResolver.resolve(
            client=mock_client,
            name=None,  # type: ignore
            strategy=mock_strategy,
            fallback_id="primary",
        )

        # Assert
        assert result is not None
        assert result.id == "primary"

    @pytest.mark.asyncio
    async def test_resolve_strips_whitespace(self, mock_client, mock_strategy):
        """Test whitespace is stripped during matching."""
        # Arrange
        mock_strategy.fetch_items.return_value = [
            {"id": "cal_123", "name": "Famille"},
        ]

        # Act
        result = await PreferenceNameResolver.resolve(
            client=mock_client,
            name="  Famille  ",  # With whitespace
            strategy=mock_strategy,
        )

        # Assert
        assert result is not None
        assert result.id == "cal_123"

    @pytest.mark.asyncio
    async def test_resolve_api_error_with_fallback(self, mock_client, mock_strategy):
        """Test fallback is returned on API error."""
        # Arrange
        mock_strategy.fetch_items.side_effect = Exception("API Error")

        # Act
        result = await PreferenceNameResolver.resolve(
            client=mock_client,
            name="Famille",
            strategy=mock_strategy,
            fallback_id="primary",
        )

        # Assert
        assert result is not None
        assert result.id == "primary"

    @pytest.mark.asyncio
    async def test_resolve_api_error_no_fallback(self, mock_client, mock_strategy):
        """Test None is returned on API error without fallback."""
        # Arrange
        mock_strategy.fetch_items.side_effect = Exception("API Error")

        # Act
        result = await PreferenceNameResolver.resolve(
            client=mock_client,
            name="Famille",
            strategy=mock_strategy,
            fallback_id=None,
        )

        # Assert
        assert result is None


class TestGoogleCalendarNameResolver:
    """Tests for Google Calendar name resolver."""

    @pytest.fixture
    def resolver(self):
        return GoogleCalendarNameResolver()

    @pytest.fixture
    def mock_calendar_client(self):
        client = MagicMock()
        client.list_calendars = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_fetch_items_calls_list_calendars(self, resolver, mock_calendar_client):
        """Test fetch_items calls client.list_calendars."""
        # Arrange
        mock_calendar_client.list_calendars.return_value = {
            "items": [{"id": "cal_1", "summary": "Test"}]
        }

        # Act
        items = await resolver.fetch_items(mock_calendar_client)

        # Assert
        mock_calendar_client.list_calendars.assert_called_once_with(max_results=100)
        assert items == [{"id": "cal_1", "summary": "Test"}]

    def test_get_item_name_returns_summary(self, resolver):
        """Test calendar name is extracted from 'summary' field."""
        item = {"id": "cal_1", "summary": "Famille", "description": "Family"}
        assert resolver.get_item_name(item) == "Famille"

    def test_get_item_id_returns_id(self, resolver):
        """Test calendar ID is extracted from 'id' field."""
        item = {"id": "cal_123", "summary": "Test"}
        assert resolver.get_item_id(item) == "cal_123"


class TestGoogleTasksListNameResolver:
    """Tests for Google Tasks list name resolver."""

    @pytest.fixture
    def resolver(self):
        return GoogleTasksListNameResolver()

    @pytest.fixture
    def mock_tasks_client(self):
        client = MagicMock()
        client.list_task_lists = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_fetch_items_calls_list_task_lists(self, resolver, mock_tasks_client):
        """Test fetch_items calls client.list_task_lists."""
        # Arrange
        mock_tasks_client.list_task_lists.return_value = {
            "items": [{"id": "list_1", "title": "My Tasks"}]
        }

        # Act
        items = await resolver.fetch_items(mock_tasks_client)

        # Assert
        mock_tasks_client.list_task_lists.assert_called_once_with(max_results=100)
        assert items == [{"id": "list_1", "title": "My Tasks"}]

    def test_get_item_name_returns_title(self, resolver):
        """Test task list name is extracted from 'title' field."""
        item = {"id": "list_1", "title": "My Tasks"}
        assert resolver.get_item_name(item) == "My Tasks"

    def test_get_item_id_returns_id(self, resolver):
        """Test task list ID is extracted from 'id' field."""
        item = {"id": "list_abc123", "title": "Test"}
        assert resolver.get_item_id(item) == "list_abc123"


class TestResolveCalendarName:
    """Tests for resolve_calendar_name convenience function."""

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.list_calendars = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_resolve_found(self, mock_client):
        """Test successful calendar name resolution."""
        # Arrange
        mock_client.list_calendars.return_value = {
            "items": [
                {"id": "cal_family", "summary": "Famille"},
                {"id": "cal_work", "summary": "Work"},
            ]
        }

        # Act
        result = await resolve_calendar_name(mock_client, "famille")

        # Assert
        assert result == "cal_family"

    @pytest.mark.asyncio
    async def test_resolve_not_found_returns_fallback(self, mock_client):
        """Test fallback is returned when calendar not found."""
        # Arrange
        mock_client.list_calendars.return_value = {"items": [{"id": "cal_work", "summary": "Work"}]}

        # Act
        result = await resolve_calendar_name(mock_client, "NonExistent", fallback="primary")

        # Assert
        assert result == "primary"

    @pytest.mark.asyncio
    async def test_resolve_empty_name_returns_fallback(self, mock_client):
        """Test empty name returns fallback without API call."""
        # Act
        result = await resolve_calendar_name(mock_client, "", fallback="primary")

        # Assert
        assert result == "primary"
        mock_client.list_calendars.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_none_name_returns_fallback(self, mock_client):
        """Test None name returns fallback."""
        # Act
        result = await resolve_calendar_name(mock_client, None, fallback="primary")

        # Assert
        assert result == "primary"


class TestResolveTaskListName:
    """Tests for resolve_task_list_name convenience function."""

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.list_task_lists = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_resolve_found(self, mock_client):
        """Test successful task list name resolution."""
        # Arrange
        mock_client.list_task_lists.return_value = {
            "items": [
                {"id": "list_main", "title": "My Tasks"},
                {"id": "list_work", "title": "Work Tasks"},
            ]
        }

        # Act - case insensitive
        result = await resolve_task_list_name(mock_client, "MY TASKS")

        # Assert
        assert result == "list_main"

    @pytest.mark.asyncio
    async def test_resolve_not_found_returns_fallback(self, mock_client):
        """Test fallback is returned when task list not found."""
        # Arrange
        mock_client.list_task_lists.return_value = {
            "items": [{"id": "list_work", "title": "Work Tasks"}]
        }

        # Act
        result = await resolve_task_list_name(mock_client, "NonExistent", fallback="@default")

        # Assert
        assert result == "@default"

    @pytest.mark.asyncio
    async def test_resolve_empty_name_returns_fallback(self, mock_client):
        """Test empty name returns fallback without API call."""
        # Act
        result = await resolve_task_list_name(mock_client, "", fallback="@default")

        # Assert
        assert result == "@default"
        mock_client.list_task_lists.assert_not_called()


class TestResolvedItem:
    """Tests for ResolvedItem dataclass."""

    def test_resolved_item_is_frozen(self):
        """Test ResolvedItem is immutable."""
        item = ResolvedItem(id="cal_123", name="Famille", exact_match=True)

        with pytest.raises(AttributeError):
            item.id = "new_id"  # type: ignore

    def test_resolved_item_equality(self):
        """Test ResolvedItem equality comparison."""
        item1 = ResolvedItem(id="cal_123", name="Famille", exact_match=True)
        item2 = ResolvedItem(id="cal_123", name="Famille", exact_match=True)
        item3 = ResolvedItem(id="cal_123", name="Famille", exact_match=False)

        assert item1 == item2
        assert item1 != item3

    def test_resolved_item_hash(self):
        """Test ResolvedItem can be used in sets/dicts."""
        item1 = ResolvedItem(id="cal_123", name="Famille", exact_match=True)
        item2 = ResolvedItem(id="cal_123", name="Famille", exact_match=True)

        # Should be hashable and equal items should have same hash
        assert hash(item1) == hash(item2)

        # Should work in sets
        items_set = {item1, item2}
        assert len(items_set) == 1
