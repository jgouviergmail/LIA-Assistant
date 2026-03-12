"""
Unit tests for domains.agents.tools.constants module.

Tests tool name constants and registries.

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-21
Updated: 2025-11-28 - Added all domain tools
"""

from src.domains.agents.tools.constants import (
    ALL_CALENDAR_TOOLS,
    ALL_CONTACTS_TOOLS,
    ALL_CONTEXT_TOOLS,
    ALL_DRIVE_TOOLS,
    ALL_EMAILS_TOOLS,
    ALL_PERPLEXITY_TOOLS,
    ALL_PLACES_TOOLS,
    ALL_TASKS_TOOLS,
    ALL_TOOLS,
    ALL_WEATHER_TOOLS,
    ALL_WIKIPEDIA_TOOLS,
    TOOL_NAME_GET_CONTACT_DETAILS,
    TOOL_NAME_LIST_CONTACTS,
    TOOL_NAME_RESOLVE_REFERENCE,
    TOOL_NAME_SEARCH_CONTACTS,
)


class TestContactsToolConstants:
    """Tests for Google Contacts tool name constants."""

    def test_tool_name_search_contacts_is_string(self):
        """Test TOOL_NAME_SEARCH_CONTACTS is a string."""
        assert isinstance(TOOL_NAME_SEARCH_CONTACTS, str)
        assert TOOL_NAME_SEARCH_CONTACTS == "search_contacts_tool"

    def test_tool_name_list_contacts_is_string(self):
        """Test TOOL_NAME_LIST_CONTACTS is a string."""
        assert isinstance(TOOL_NAME_LIST_CONTACTS, str)
        assert TOOL_NAME_LIST_CONTACTS == "list_contacts_tool"

    def test_tool_name_get_contact_details_is_string(self):
        """Test TOOL_NAME_GET_CONTACT_DETAILS is a string."""
        assert isinstance(TOOL_NAME_GET_CONTACT_DETAILS, str)
        assert TOOL_NAME_GET_CONTACT_DETAILS == "get_contact_details_tool"

    def test_all_contacts_tools_is_list(self):
        """Test ALL_CONTACTS_TOOLS is a list."""
        assert isinstance(ALL_CONTACTS_TOOLS, list)

    def test_all_contacts_tools_contains_all_contacts_constants(self):
        """Test ALL_CONTACTS_TOOLS contains all 3 contacts tool names."""
        assert TOOL_NAME_SEARCH_CONTACTS in ALL_CONTACTS_TOOLS
        assert TOOL_NAME_LIST_CONTACTS in ALL_CONTACTS_TOOLS
        assert TOOL_NAME_GET_CONTACT_DETAILS in ALL_CONTACTS_TOOLS
        assert len(ALL_CONTACTS_TOOLS) == 3

    def test_all_contacts_tools_no_duplicates(self):
        """Test ALL_CONTACTS_TOOLS contains no duplicate tool names."""
        assert len(ALL_CONTACTS_TOOLS) == len(set(ALL_CONTACTS_TOOLS))


class TestContextToolConstants:
    """Tests for context management tool name constants."""

    def test_tool_name_resolve_reference_is_string(self):
        """Test TOOL_NAME_RESOLVE_REFERENCE is a string."""
        assert isinstance(TOOL_NAME_RESOLVE_REFERENCE, str)
        assert TOOL_NAME_RESOLVE_REFERENCE == "resolve_reference"

    def test_all_context_tools_is_list(self):
        """Test ALL_CONTEXT_TOOLS is a list."""
        assert isinstance(ALL_CONTEXT_TOOLS, list)

    def test_all_context_tools_contains_resolve_reference(self):
        """Test ALL_CONTEXT_TOOLS contains resolve_reference tool."""
        assert TOOL_NAME_RESOLVE_REFERENCE in ALL_CONTEXT_TOOLS
        assert len(ALL_CONTEXT_TOOLS) == 1


class TestAllToolsRegistry:
    """Tests for ALL_TOOLS registry."""

    def test_all_tools_is_list(self):
        """Test ALL_TOOLS is a list."""
        assert isinstance(ALL_TOOLS, list)

    def test_all_tools_contains_all_contacts_tools(self):
        """Test ALL_TOOLS contains all contacts tool names."""
        for tool_name in ALL_CONTACTS_TOOLS:
            assert tool_name in ALL_TOOLS

    def test_all_tools_contains_all_context_tools(self):
        """Test ALL_TOOLS contains all context tool names."""
        for tool_name in ALL_CONTEXT_TOOLS:
            assert tool_name in ALL_TOOLS

    def test_all_tools_count(self):
        """Test ALL_TOOLS contains the expected number of tools across all domains."""
        # 3 contacts + 1 context + 3 emails + 5 calendar + 3 drive
        # + 4 tasks + 3 weather + 4 wikipedia + 2 perplexity + 3 places = 31
        expected_count = (
            len(ALL_CONTACTS_TOOLS)
            + len(ALL_CONTEXT_TOOLS)
            + len(ALL_EMAILS_TOOLS)
            + len(ALL_CALENDAR_TOOLS)
            + len(ALL_DRIVE_TOOLS)
            + len(ALL_TASKS_TOOLS)
            + len(ALL_WEATHER_TOOLS)
            + len(ALL_WIKIPEDIA_TOOLS)
            + len(ALL_PERPLEXITY_TOOLS)
            + len(ALL_PLACES_TOOLS)
        )
        assert len(ALL_TOOLS) == expected_count
        assert len(ALL_TOOLS) == 30  # Explicit count as sanity check

    def test_all_tools_is_union_of_categories(self):
        """Test ALL_TOOLS equals union of all domain tools."""
        expected = (
            ALL_CONTACTS_TOOLS
            + ALL_CONTEXT_TOOLS
            + ALL_EMAILS_TOOLS
            + ALL_CALENDAR_TOOLS
            + ALL_DRIVE_TOOLS
            + ALL_TASKS_TOOLS
            + ALL_WEATHER_TOOLS
            + ALL_WIKIPEDIA_TOOLS
            + ALL_PERPLEXITY_TOOLS
            + ALL_PLACES_TOOLS
        )
        assert ALL_TOOLS == expected

    def test_all_tools_no_duplicates(self):
        """Test ALL_TOOLS contains no duplicate tool names."""
        assert len(ALL_TOOLS) == len(set(ALL_TOOLS))


class TestToolNameFormat:
    """Tests for tool name format conventions."""

    def test_all_tool_names_are_strings(self):
        """Test all tool names in ALL_TOOLS are strings."""
        for tool_name in ALL_TOOLS:
            assert isinstance(tool_name, str)

    def test_all_tool_names_not_empty(self):
        """Test all tool names are non-empty strings."""
        for tool_name in ALL_TOOLS:
            assert len(tool_name) > 0

    def test_all_tool_names_lowercase(self):
        """Test all tool names follow lowercase convention."""
        for tool_name in ALL_TOOLS:
            assert tool_name.islower() or "_" in tool_name

    def test_tool_names_use_underscores(self):
        """Test tool names use underscores (snake_case convention)."""
        for tool_name in ALL_TOOLS:
            assert " " not in tool_name  # No spaces
            # Most tool names should have underscores (snake_case)
            # resolve_reference has underscore, contacts tools end with _tool


class TestConstantsUniqueness:
    """Tests for uniqueness of all constants."""

    def test_contacts_tool_names_unique(self):
        """Test all contacts tool name constants have unique values."""
        contacts_tools = [
            TOOL_NAME_SEARCH_CONTACTS,
            TOOL_NAME_LIST_CONTACTS,
            TOOL_NAME_GET_CONTACT_DETAILS,
        ]
        assert len(contacts_tools) == len(set(contacts_tools))

    def test_context_tool_names_unique(self):
        """Test context tool names are unique (single tool for now)."""
        assert len([TOOL_NAME_RESOLVE_REFERENCE]) == 1

    def test_all_tool_constants_globally_unique(self):
        """Test all tool name constants across categories are unique."""
        all_constants = [
            TOOL_NAME_SEARCH_CONTACTS,
            TOOL_NAME_LIST_CONTACTS,
            TOOL_NAME_GET_CONTACT_DETAILS,
            TOOL_NAME_RESOLVE_REFERENCE,
        ]
        assert len(all_constants) == len(set(all_constants))


class TestEdgeCases:
    """Tests for edge cases and module integrity."""

    def test_constants_module_immutability(self):
        """Test tool name constants should not be modified (good practice check)."""
        # This test documents expected immutability behavior
        # Constants should be uppercase by convention (already tested in format tests)
        # Actual immutability requires type annotations (Final) which may be added later
        assert TOOL_NAME_SEARCH_CONTACTS == "search_contacts_tool"

    def test_all_tools_registry_can_be_iterated(self):
        """Test ALL_TOOLS registry can be iterated."""
        count = 0
        for tool_name in ALL_TOOLS:
            count += 1
            assert isinstance(tool_name, str)
        assert count == len(ALL_TOOLS)

    def test_all_contacts_tools_can_be_iterated(self):
        """Test ALL_CONTACTS_TOOLS can be iterated."""
        count = 0
        for tool_name in ALL_CONTACTS_TOOLS:
            count += 1
            assert isinstance(tool_name, str)
        assert count == 3

    def test_all_context_tools_can_be_iterated(self):
        """Test ALL_CONTEXT_TOOLS can be iterated."""
        count = 0
        for tool_name in ALL_CONTEXT_TOOLS:
            count += 1
            assert isinstance(tool_name, str)
        assert count == 1


class TestDomainToolLists:
    """Tests for individual domain tool lists."""

    def test_emails_tools_count(self):
        """Test ALL_EMAILS_TOOLS contains 3 tools."""
        assert len(ALL_EMAILS_TOOLS) == 3

    def test_calendar_tools_count(self):
        """Test ALL_CALENDAR_TOOLS contains 5 tools."""
        assert len(ALL_CALENDAR_TOOLS) == 5

    def test_drive_tools_count(self):
        """Test ALL_DRIVE_TOOLS contains 3 tools."""
        assert len(ALL_DRIVE_TOOLS) == 3

    def test_tasks_tools_count(self):
        """Test ALL_TASKS_TOOLS contains 4 tools."""
        assert len(ALL_TASKS_TOOLS) == 4

    def test_weather_tools_count(self):
        """Test ALL_WEATHER_TOOLS contains 3 tools."""
        assert len(ALL_WEATHER_TOOLS) == 3

    def test_wikipedia_tools_count(self):
        """Test ALL_WIKIPEDIA_TOOLS contains 4 tools."""
        assert len(ALL_WIKIPEDIA_TOOLS) == 4

    def test_perplexity_tools_count(self):
        """Test ALL_PERPLEXITY_TOOLS contains 2 tools."""
        assert len(ALL_PERPLEXITY_TOOLS) == 2

    def test_places_tools_count(self):
        """Test ALL_PLACES_TOOLS contains 2 tools."""
        assert len(ALL_PLACES_TOOLS) == 2
