"""
Unit tests for string-to-list coercion in GetContactDetailsTool.

Issue #54: The planner generates Jinja2 templates that produce strings
instead of lists for resource_names. These tests verify that the coercion
works correctly.

These tests are UNIT tests and directly test the execute_api_call() method
without going through the LangChain/LangGraph infrastructure (ToolRuntime, etc.).
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.tools.google_contacts_tools import GetContactDetailsTool


# Mock normalize_field_names to avoid registry dependency
@pytest.fixture(autouse=True)
def mock_normalize_fields():
    """Mock normalize_field_names to avoid AgentRegistry dependency."""
    with patch(
        "src.domains.agents.tools.google_contacts_tools.normalize_field_names",
        return_value=["names", "emailAddresses", "phoneNumbers"],
    ):
        yield


class TestGetContactDetailsToolCoercion:
    """Tests unitaires pour la coercion string→list (Issue #54)."""

    @pytest.fixture
    def tool(self):
        """Create tool instance."""
        return GetContactDetailsTool()

    @pytest.fixture
    def mock_client(self):
        """Create mock GooglePeopleClient.

        Note: _execute_batch() calls client.get_person() for each contact,
        not client.get_people_batch(). This is by design for concurrent fetching.
        """
        client = MagicMock()
        # get_person is used by both single mode AND batch mode (called per contact)
        client.get_person = AsyncMock(
            return_value={
                "resourceName": "people/c123",
                "names": [{"displayName": "John Doe"}],
                "emailAddresses": [{"value": "john@example.com"}],
            }
        )
        return client

    @pytest.mark.asyncio
    async def test_resource_names_string_coercion(self, tool, mock_client):
        """Test that string resource_names is coerced to list.

        This is the core test for Issue #54:
        - Planner generates: resource_names="people/c123" (string)
        - Tool should accept and coerce to: ["people/c123"] (list)
        """
        user_id = uuid4()

        # KEY TEST: Pass string instead of list
        # This simulates the Jinja2 template evaluation result
        result = await tool.execute_api_call(
            client=mock_client,
            user_id=user_id,
            resource_names="people/c6005623555827615994",  # STRING, not list!
        )

        # Verify the call succeeded (coercion worked)
        assert result is not None
        # Batch mode calls get_person for each contact in the list
        # With coercion, string becomes list of 1, so get_person called once
        mock_client.get_person.assert_called_once()

    @pytest.mark.asyncio
    async def test_resource_names_list_still_works(self, tool, mock_client):
        """Test that list resource_names still works after coercion code added."""
        user_id = uuid4()

        # Normal list input - should still work
        result = await tool.execute_api_call(
            client=mock_client,
            user_id=user_id,
            resource_names=["people/c123", "people/c456"],  # list as expected
        )

        assert result is not None
        # Batch mode: get_person called once per contact in list
        assert mock_client.get_person.call_count == 2

    @pytest.mark.asyncio
    async def test_resource_name_singular_still_works(self, tool, mock_client):
        """Test that resource_name (singular) still works."""
        user_id = uuid4()

        # Singular mode (not batch)
        result = await tool.execute_api_call(
            client=mock_client,
            user_id=user_id,
            resource_name="people/c123",  # singular parameter
        )

        assert result is not None
        # Single mode calls get_person once
        mock_client.get_person.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_string_coercion(self, tool, mock_client):
        """Test that empty string resource_names is coerced to list.

        When Jinja2 conditional evaluates to empty, the coercion still works.
        The empty string becomes [""] which triggers batch mode.
        """
        user_id = uuid4()

        # Empty string should be coerced to [""]
        await tool.execute_api_call(
            client=mock_client,
            user_id=user_id,
            resource_names="",  # empty string
        )
        # Coercion converts "" to [""], then batch mode is triggered
        # get_person called once with empty string
        mock_client.get_person.assert_called_once()

    @pytest.mark.asyncio
    async def test_neither_resource_name_nor_resource_names_raises(self, tool, mock_client):
        """Test that missing both parameters raises ValueError."""
        user_id = uuid4()

        with pytest.raises(ValueError, match="Either resource_name or resource_names"):
            await tool.execute_api_call(
                client=mock_client,
                user_id=user_id,
                # Neither resource_name nor resource_names provided
            )

    @pytest.mark.asyncio
    async def test_both_resource_name_and_resource_names_raises(self, tool, mock_client):
        """Test that providing both parameters raises ValueError."""
        user_id = uuid4()

        with pytest.raises(ValueError, match="mutually exclusive"):
            await tool.execute_api_call(
                client=mock_client,
                user_id=user_id,
                resource_name="people/c123",
                resource_names=["people/c456"],  # Both provided - error!
            )

    @pytest.mark.asyncio
    async def test_coercion_preserves_resource_name_value(self, tool, mock_client):
        """Test that the coerced value is correctly passed to API."""
        user_id = uuid4()
        expected_resource = "people/c6005623555827615994"

        await tool.execute_api_call(
            client=mock_client,
            user_id=user_id,
            resource_names=expected_resource,  # string
        )

        # Verify get_person was called with the coerced value
        mock_client.get_person.assert_called_once()
        call_args = mock_client.get_person.call_args
        # The resource_name arg should be the original string value
        assert call_args.kwargs["resource_name"] == expected_resource


class TestCoercionEdgeCases:
    """Edge cases for string→list coercion."""

    @pytest.fixture
    def tool(self):
        return GetContactDetailsTool()

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.get_person = AsyncMock(
            return_value={
                "resourceName": "people/c123",
                "names": [{"displayName": "Test"}],
            }
        )
        return client

    @pytest.mark.asyncio
    async def test_whitespace_string_is_coerced(self, tool, mock_client):
        """Test that whitespace-only string is coerced (not treated as empty)."""
        user_id = uuid4()

        # Whitespace string should be coerced to ["  "] (a list with whitespace)
        await tool.execute_api_call(
            client=mock_client,
            user_id=user_id,
            resource_names="  ",  # whitespace
        )

        # get_person called once with the whitespace string
        mock_client.get_person.assert_called_once()

    @pytest.mark.asyncio
    async def test_dict_list_is_not_affected(self, tool, mock_client):
        """Test that list of dicts (another valid input type) is not affected."""
        user_id = uuid4()

        # resource_names can also be list[dict] for batch with metadata
        dict_list = [{"resource_name": "people/c123", "etag": "abc"}]

        await tool.execute_api_call(
            client=mock_client,
            user_id=user_id,
            resource_names=dict_list,
        )

        # get_person called once (one item in list)
        mock_client.get_person.assert_called_once()


# ============================================================================
# Tests CSV String Coercion (Issue #dupond)
# ============================================================================


class TestCSVStringCoercion:
    """Tests for CSV string coercion (Issue #dupond).

    When Jinja templates produce CSV strings like "people/c1,people/c2",
    the tool should parse them into arrays ["people/c1", "people/c2"].
    """

    @pytest.fixture
    def tool(self):
        return GetContactDetailsTool()

    @pytest.fixture
    def mock_client(self):
        client = MagicMock()
        client.get_person = AsyncMock(
            return_value={
                "resourceName": "people/c123",
                "names": [{"displayName": "Test User"}],
            }
        )
        return client

    @pytest.mark.asyncio
    async def test_csv_string_is_parsed_to_list(self, tool, mock_client):
        """Test that CSV string with commas is parsed to list.

        Jinja template like:
            {% for item in steps.group.members %}{{ item.resource_name }}{% if not loop.last %},{% endif %}{% endfor %}
        produces: "people/c123,people/c456,people/c789"
        which should be parsed to: ["people/c123", "people/c456", "people/c789"]
        """
        user_id = uuid4()

        # CSV string with 3 resource names
        csv_input = "people/c123,people/c456,people/c789"

        await tool.execute_api_call(
            client=mock_client,
            user_id=user_id,
            resource_names=csv_input,
        )

        # Should call get_person 3 times (one per parsed resource name)
        assert mock_client.get_person.call_count == 3

        # Verify each call was made with correct resource name
        calls = mock_client.get_person.call_args_list
        assert calls[0].kwargs["resource_name"] == "people/c123"
        assert calls[1].kwargs["resource_name"] == "people/c456"
        assert calls[2].kwargs["resource_name"] == "people/c789"

    @pytest.mark.asyncio
    async def test_csv_string_with_whitespace_is_trimmed(self, tool, mock_client):
        """Test that whitespace around CSV values is stripped."""
        user_id = uuid4()

        # CSV with extra whitespace
        csv_input = "people/c123, people/c456 , people/c789"

        await tool.execute_api_call(
            client=mock_client,
            user_id=user_id,
            resource_names=csv_input,
        )

        assert mock_client.get_person.call_count == 3
        calls = mock_client.get_person.call_args_list
        assert calls[0].kwargs["resource_name"] == "people/c123"
        assert calls[1].kwargs["resource_name"] == "people/c456"  # trimmed
        assert calls[2].kwargs["resource_name"] == "people/c789"  # trimmed

    @pytest.mark.asyncio
    async def test_single_resource_name_without_comma_is_wrapped(self, tool, mock_client):
        """Test that single resource name (no comma) is wrapped in list."""
        user_id = uuid4()

        # Single resource name, no comma
        single_input = "people/c123"

        await tool.execute_api_call(
            client=mock_client,
            user_id=user_id,
            resource_names=single_input,
        )

        # Should call get_person once
        assert mock_client.get_person.call_count == 1
        assert mock_client.get_person.call_args.kwargs["resource_name"] == "people/c123"

    @pytest.mark.asyncio
    async def test_string_without_people_prefix_is_wrapped_not_split(self, tool, mock_client):
        """Test that string without 'people/' prefix is NOT treated as CSV.

        Only strings that contain 'people/' AND comma should be split.
        This prevents accidental splitting of other string values.
        """
        user_id = uuid4()

        # String with comma but no 'people/' prefix - should be wrapped, not split
        input_with_comma = "some,other,value"

        await tool.execute_api_call(
            client=mock_client,
            user_id=user_id,
            resource_names=input_with_comma,
        )

        # Should call get_person once (wrapped as ["some,other,value"], not split)
        assert mock_client.get_person.call_count == 1
        assert mock_client.get_person.call_args.kwargs["resource_name"] == "some,other,value"

    @pytest.mark.asyncio
    async def test_empty_csv_segments_are_filtered(self, tool, mock_client):
        """Test that empty segments from double commas are filtered out."""
        user_id = uuid4()

        # CSV with empty segment (double comma)
        csv_input = "people/c123,,people/c456"

        await tool.execute_api_call(
            client=mock_client,
            user_id=user_id,
            resource_names=csv_input,
        )

        # Should call get_person twice (empty segment filtered)
        assert mock_client.get_person.call_count == 2
        calls = mock_client.get_person.call_args_list
        assert calls[0].kwargs["resource_name"] == "people/c123"
        assert calls[1].kwargs["resource_name"] == "people/c456"

    @pytest.mark.asyncio
    async def test_csv_with_trailing_comma(self, tool, mock_client):
        """Test that trailing comma is handled correctly."""
        user_id = uuid4()

        # CSV with trailing comma
        csv_input = "people/c123,people/c456,"

        await tool.execute_api_call(
            client=mock_client,
            user_id=user_id,
            resource_names=csv_input,
        )

        # Should call get_person twice (trailing empty filtered)
        assert mock_client.get_person.call_count == 2
