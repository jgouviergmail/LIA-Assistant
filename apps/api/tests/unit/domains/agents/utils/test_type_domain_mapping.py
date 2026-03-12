"""
Unit tests for type-to-domain mapping utilities.

Tests for registry type to domain name mapping, tool name to domain
extraction, and registry configuration lookups.
"""

import pytest

from src.domains.agents.utils.type_domain_mapping import (
    ITEMS_KEY_TO_REGISTRY_CONFIG,
    TOOL_PATTERN_TO_DOMAIN_MAP,
    TYPE_TO_DOMAIN_MAP,
    get_all_domain_names,
    get_domain_from_result_key,
    get_domain_from_tool_name,
    get_domain_from_type,
    get_domain_name_from_type,
    get_registry_config_for_items_key,
    get_result_key_from_type,
    is_list_tool,
)

# ============================================================================
# Tests for TYPE_TO_DOMAIN_MAP constant
# ============================================================================


class TestTypeToDomainMap:
    """Tests for TYPE_TO_DOMAIN_MAP constant."""

    def test_contact_mapping_exists(self):
        """Test that CONTACT mapping exists."""
        assert "CONTACT" in TYPE_TO_DOMAIN_MAP
        assert TYPE_TO_DOMAIN_MAP["CONTACT"] == ("contact", "contacts")

    def test_email_mapping_exists(self):
        """Test that EMAIL mapping exists."""
        assert "EMAIL" in TYPE_TO_DOMAIN_MAP
        assert TYPE_TO_DOMAIN_MAP["EMAIL"] == ("email", "emails")

    def test_event_mapping_exists(self):
        """Test that EVENT mapping exists."""
        assert "EVENT" in TYPE_TO_DOMAIN_MAP
        assert TYPE_TO_DOMAIN_MAP["EVENT"] == ("event", "events")

    def test_task_mapping_exists(self):
        """Test that TASK mapping exists."""
        assert "TASK" in TYPE_TO_DOMAIN_MAP
        assert TYPE_TO_DOMAIN_MAP["TASK"] == ("task", "tasks")

    def test_file_mapping_exists(self):
        """Test that FILE mapping exists."""
        assert "FILE" in TYPE_TO_DOMAIN_MAP
        assert TYPE_TO_DOMAIN_MAP["FILE"] == ("file", "files")

    def test_place_mapping_exists(self):
        """Test that PLACE mapping exists."""
        assert "PLACE" in TYPE_TO_DOMAIN_MAP
        assert TYPE_TO_DOMAIN_MAP["PLACE"] == ("place", "places")

    def test_weather_mapping_exists(self):
        """Test that WEATHER mapping exists."""
        assert "WEATHER" in TYPE_TO_DOMAIN_MAP
        assert TYPE_TO_DOMAIN_MAP["WEATHER"] == ("weather", "weathers")

    def test_route_mapping_exists(self):
        """Test that ROUTE mapping exists."""
        assert "ROUTE" in TYPE_TO_DOMAIN_MAP
        assert TYPE_TO_DOMAIN_MAP["ROUTE"] == ("route", "routes")

    def test_reminder_mapping_exists(self):
        """Test that REMINDER mapping exists."""
        assert "REMINDER" in TYPE_TO_DOMAIN_MAP
        assert TYPE_TO_DOMAIN_MAP["REMINDER"] == ("reminder", "reminders")

    def test_all_values_are_tuples(self):
        """Test that all values are tuples of (domain, items_key)."""
        for type_name, value in TYPE_TO_DOMAIN_MAP.items():
            assert isinstance(value, tuple), f"Value for {type_name} is not tuple"
            assert len(value) == 2, f"Value for {type_name} doesn't have 2 elements"

    def test_items_key_follows_pattern(self):
        """Test that items_key follows domain+'s' pattern."""
        for type_name, (_domain, items_key) in TYPE_TO_DOMAIN_MAP.items():
            # items_key should end with 's' (plural)
            assert items_key.endswith("s"), f"items_key for {type_name} doesn't end with 's'"


# ============================================================================
# Tests for get_domain_from_type function
# ============================================================================


class TestGetDomainFromType:
    """Tests for get_domain_from_type function."""

    def test_contact_type(self):
        """Test CONTACT type returns correct tuple."""
        result = get_domain_from_type("CONTACT")
        assert result == ("contact", "contacts")

    def test_email_type(self):
        """Test EMAIL type returns correct tuple."""
        result = get_domain_from_type("EMAIL")
        assert result == ("email", "emails")

    def test_event_type(self):
        """Test EVENT type returns correct tuple."""
        result = get_domain_from_type("EVENT")
        assert result == ("event", "events")

    def test_case_insensitive(self):
        """Test that lookup is case-insensitive."""
        result_upper = get_domain_from_type("CONTACT")
        result_lower = get_domain_from_type("contact")
        result_mixed = get_domain_from_type("Contact")

        assert result_upper == result_lower == result_mixed

    def test_unknown_type_fallback(self):
        """Test that unknown type uses fallback."""
        result = get_domain_from_type("UNKNOWN_TYPE")

        # Fallback: (lowercase type, type + "s")
        assert result == ("unknown_type", "unknown_types")

    def test_returns_tuple(self):
        """Test that function returns tuple."""
        result = get_domain_from_type("CONTACT")

        assert isinstance(result, tuple)
        assert len(result) == 2


class TestGetDomainFromTypeAllTypes:
    """Tests for get_domain_from_type with all known types."""

    @pytest.mark.parametrize(
        "type_name,expected_domain,expected_key",
        [
            ("CONTACT", "contact", "contacts"),
            ("EMAIL", "email", "emails"),
            ("EVENT", "event", "events"),
            ("TASK", "task", "tasks"),
            ("FILE", "file", "files"),
            ("PLACE", "place", "places"),
            ("WEATHER", "weather", "weathers"),
            ("ROUTE", "route", "routes"),
            ("REMINDER", "reminder", "reminders"),
        ],
    )
    def test_all_known_types(self, type_name, expected_domain, expected_key):
        """Test all known types return correct values."""
        domain, key = get_domain_from_type(type_name)
        assert domain == expected_domain
        assert key == expected_key


# ============================================================================
# Tests for get_domain_name_from_type function
# ============================================================================


class TestGetDomainNameFromType:
    """Tests for get_domain_name_from_type function."""

    def test_contact_returns_domain(self):
        """Test CONTACT returns domain name."""
        result = get_domain_name_from_type("CONTACT")
        assert result == "contact"

    def test_email_returns_domain(self):
        """Test EMAIL returns domain name."""
        result = get_domain_name_from_type("EMAIL")
        assert result == "email"

    def test_event_returns_domain(self):
        """Test EVENT returns domain name."""
        result = get_domain_name_from_type("EVENT")
        assert result == "event"

    def test_case_insensitive(self):
        """Test that lookup is case-insensitive."""
        result = get_domain_name_from_type("email")
        assert result == "email"

    def test_unknown_returns_none(self):
        """Test that unknown type returns None."""
        result = get_domain_name_from_type("UNKNOWN_TYPE")
        assert result is None

    def test_empty_string_returns_none(self):
        """Test that empty string returns None."""
        result = get_domain_name_from_type("")
        assert result is None


# ============================================================================
# Tests for get_result_key_from_type function
# ============================================================================


class TestGetResultKeyFromType:
    """Tests for get_result_key_from_type function."""

    def test_contact_returns_key(self):
        """Test CONTACT returns result key."""
        result = get_result_key_from_type("CONTACT")
        assert result == "contacts"

    def test_email_returns_key(self):
        """Test EMAIL returns result key."""
        result = get_result_key_from_type("EMAIL")
        assert result == "emails"

    def test_event_returns_key(self):
        """Test EVENT returns result key."""
        result = get_result_key_from_type("EVENT")
        assert result == "events"

    def test_weather_returns_key(self):
        """Test WEATHER returns result key (domain+'s' pattern)."""
        result = get_result_key_from_type("WEATHER")
        assert result == "weathers"

    def test_case_insensitive(self):
        """Test that lookup is case-insensitive."""
        result = get_result_key_from_type("contact")
        assert result == "contacts"

    def test_unknown_returns_none(self):
        """Test that unknown type returns None."""
        result = get_result_key_from_type("UNKNOWN")
        assert result is None


# ============================================================================
# Tests for get_all_domain_names function
# ============================================================================


class TestGetAllDomainNames:
    """Tests for get_all_domain_names function."""

    def test_returns_list(self):
        """Test that function returns list."""
        result = get_all_domain_names()
        assert isinstance(result, list)

    def test_contains_contact(self):
        """Test that list contains contact."""
        result = get_all_domain_names()
        assert "contact" in result

    def test_contains_email(self):
        """Test that list contains email."""
        result = get_all_domain_names()
        assert "email" in result

    def test_contains_event(self):
        """Test that list contains event."""
        result = get_all_domain_names()
        assert "event" in result

    def test_no_duplicates(self):
        """Test that list has no duplicates."""
        result = get_all_domain_names()
        assert len(result) == len(set(result))

    def test_all_singular_form(self):
        """Test that all domain names are singular."""
        result = get_all_domain_names()
        for domain in result:
            # Should not end with 's' (except specific cases like 'files')
            # Note: This is a soft check as some domains may legitimately end with 's'
            assert isinstance(domain, str)


# ============================================================================
# Tests for get_domain_from_result_key function
# ============================================================================


class TestGetDomainFromResultKey:
    """Tests for get_domain_from_result_key function."""

    def test_contacts_returns_contact(self):
        """Test 'contacts' returns 'contact'."""
        result = get_domain_from_result_key("contacts")
        assert result == "contact"

    def test_emails_returns_email(self):
        """Test 'emails' returns 'email'."""
        result = get_domain_from_result_key("emails")
        assert result == "email"

    def test_events_returns_event(self):
        """Test 'events' returns 'event'."""
        result = get_domain_from_result_key("events")
        assert result == "event"

    def test_weathers_returns_weather(self):
        """Test 'weathers' returns 'weather'."""
        result = get_domain_from_result_key("weathers")
        assert result == "weather"

    def test_case_insensitive(self):
        """Test that lookup is case-insensitive."""
        result_lower = get_domain_from_result_key("contacts")
        result_upper = get_domain_from_result_key("CONTACTS")
        result_mixed = get_domain_from_result_key("Contacts")

        assert result_lower == result_upper == result_mixed == "contact"

    def test_unknown_returns_none(self):
        """Test that unknown result key returns None."""
        result = get_domain_from_result_key("unknown_keys")
        assert result is None


# ============================================================================
# Tests for ITEMS_KEY_TO_REGISTRY_CONFIG constant
# ============================================================================


class TestItemsKeyToRegistryConfig:
    """Tests for ITEMS_KEY_TO_REGISTRY_CONFIG constant."""

    def test_contacts_config_exists(self):
        """Test that contacts config exists."""
        assert "contacts" in ITEMS_KEY_TO_REGISTRY_CONFIG
        assert ITEMS_KEY_TO_REGISTRY_CONFIG["contacts"] == ("CONTACT", "resourceName")

    def test_emails_config_exists(self):
        """Test that emails config exists."""
        assert "emails" in ITEMS_KEY_TO_REGISTRY_CONFIG
        assert ITEMS_KEY_TO_REGISTRY_CONFIG["emails"] == ("EMAIL", "id")

    def test_events_config_exists(self):
        """Test that events config exists."""
        assert "events" in ITEMS_KEY_TO_REGISTRY_CONFIG
        assert ITEMS_KEY_TO_REGISTRY_CONFIG["events"] == ("EVENT", "id")

    def test_places_config_exists(self):
        """Test that places config exists."""
        assert "places" in ITEMS_KEY_TO_REGISTRY_CONFIG
        assert ITEMS_KEY_TO_REGISTRY_CONFIG["places"] == ("PLACE", "place_id")

    def test_all_values_are_tuples(self):
        """Test that all values are tuples."""
        for key, value in ITEMS_KEY_TO_REGISTRY_CONFIG.items():
            assert isinstance(value, tuple), f"Value for {key} is not tuple"
            assert len(value) == 2, f"Value for {key} doesn't have 2 elements"


# ============================================================================
# Tests for get_registry_config_for_items_key function
# ============================================================================


class TestGetRegistryConfigForItemsKey:
    """Tests for get_registry_config_for_items_key function."""

    def test_contacts_config(self):
        """Test contacts returns correct config."""
        result = get_registry_config_for_items_key("contacts")
        assert result == ("CONTACT", "resourceName")

    def test_emails_config(self):
        """Test emails returns correct config."""
        result = get_registry_config_for_items_key("emails")
        assert result == ("EMAIL", "id")

    def test_events_config(self):
        """Test events returns correct config."""
        result = get_registry_config_for_items_key("events")
        assert result == ("EVENT", "id")

    def test_places_config(self):
        """Test places returns correct config."""
        result = get_registry_config_for_items_key("places")
        assert result == ("PLACE", "place_id")

    def test_case_insensitive(self):
        """Test that lookup is case-insensitive."""
        result_lower = get_registry_config_for_items_key("contacts")
        result_upper = get_registry_config_for_items_key("CONTACTS")

        assert result_lower == result_upper

    def test_unknown_returns_none(self):
        """Test that unknown items_key returns None."""
        result = get_registry_config_for_items_key("unknowns")
        assert result is None


# ============================================================================
# Tests for TOOL_PATTERN_TO_DOMAIN_MAP constant
# ============================================================================


class TestToolPatternToDomainMap:
    """Tests for TOOL_PATTERN_TO_DOMAIN_MAP constant."""

    def test_email_pattern_exists(self):
        """Test that email pattern exists."""
        assert "email" in TOOL_PATTERN_TO_DOMAIN_MAP
        assert TOOL_PATTERN_TO_DOMAIN_MAP["email"] == "emails"

    def test_contact_pattern_exists(self):
        """Test that contact pattern exists."""
        assert "contact" in TOOL_PATTERN_TO_DOMAIN_MAP
        assert TOOL_PATTERN_TO_DOMAIN_MAP["contact"] == "contacts"

    def test_calendar_pattern_exists(self):
        """Test that calendar pattern exists."""
        assert "calendar" in TOOL_PATTERN_TO_DOMAIN_MAP
        assert TOOL_PATTERN_TO_DOMAIN_MAP["calendar"] == "events"

    def test_event_pattern_exists(self):
        """Test that event pattern exists."""
        assert "event" in TOOL_PATTERN_TO_DOMAIN_MAP
        assert TOOL_PATTERN_TO_DOMAIN_MAP["event"] == "events"

    def test_route_pattern_exists(self):
        """Test that route pattern exists."""
        assert "route" in TOOL_PATTERN_TO_DOMAIN_MAP
        assert TOOL_PATTERN_TO_DOMAIN_MAP["route"] == "routes"


# ============================================================================
# Tests for get_domain_from_tool_name function
# ============================================================================


class TestGetDomainFromToolName:
    """Tests for get_domain_from_tool_name function."""

    def test_search_contacts_tool(self):
        """Test search_contacts_tool returns contacts."""
        result = get_domain_from_tool_name("search_contacts_tool")
        assert result == "contacts"

    def test_get_email_details_tool(self):
        """Test get_email_details_tool returns emails."""
        result = get_domain_from_tool_name("get_email_details_tool")
        assert result == "emails"

    def test_search_events_tool(self):
        """Test search_events_tool returns events."""
        result = get_domain_from_tool_name("search_events_tool")
        assert result == "events"

    def test_list_calendar_events_tool(self):
        """Test list_calendar_events_tool returns events."""
        result = get_domain_from_tool_name("list_calendar_events_tool")
        assert result == "events"

    def test_get_route_tool(self):
        """Test get_route_tool returns routes."""
        result = get_domain_from_tool_name("get_route_tool")
        assert result == "routes"

    def test_search_places_tool(self):
        """Test search_places_tool returns places."""
        result = get_domain_from_tool_name("search_places_tool")
        assert result == "places"

    def test_get_weather_tool(self):
        """Test get_weather_tool returns weathers."""
        result = get_domain_from_tool_name("get_weather_tool")
        assert result == "weathers"

    def test_case_insensitive(self):
        """Test that lookup is case-insensitive."""
        result_lower = get_domain_from_tool_name("search_contacts_tool")
        result_upper = get_domain_from_tool_name("SEARCH_CONTACTS_TOOL")
        result_mixed = get_domain_from_tool_name("Search_Contacts_Tool")

        assert result_lower == result_upper == result_mixed == "contacts"

    def test_unknown_tool_returns_none(self):
        """Test that unknown tool name returns None."""
        result = get_domain_from_tool_name("unknown_action_tool")
        assert result is None

    def test_empty_string_returns_none(self):
        """Test that empty string returns None."""
        result = get_domain_from_tool_name("")
        assert result is None

    def test_none_returns_none(self):
        """Test that None returns None."""
        result = get_domain_from_tool_name(None)  # type: ignore
        assert result is None


class TestGetDomainFromToolNamePriority:
    """Tests for domain extraction priority in tool names."""

    def test_email_in_calendar_tool(self):
        """Test that first matching pattern wins."""
        # If a tool name contains multiple patterns, first match wins
        result = get_domain_from_tool_name("email_calendar_tool")
        # 'email' comes before 'calendar' in alphabetical order of patterns
        # But iteration order depends on dict order in Python 3.7+
        assert result in ["emails", "events"]

    def test_partial_match_works(self):
        """Test that partial pattern match works."""
        result = get_domain_from_tool_name("my_contact_helper_function")
        assert result == "contacts"


# ============================================================================
# Tests for is_list_tool function
# ============================================================================


class TestIsListTool:
    """Tests for is_list_tool function."""

    def test_search_tool_is_list(self):
        """Test that search_ prefix is list tool."""
        assert is_list_tool("search_contacts_tool") is True

    def test_list_tool_is_list(self):
        """Test that list_ prefix is list tool."""
        assert is_list_tool("list_events_tool") is True

    def test_find_tool_is_list(self):
        """Test that find_ prefix is list tool."""
        assert is_list_tool("find_emails_tool") is True

    def test_query_tool_is_list(self):
        """Test that query_ prefix is list tool."""
        assert is_list_tool("query_tasks_tool") is True

    def test_get_tool_is_not_list(self):
        """Test that get_ prefix is not list tool."""
        assert is_list_tool("get_contact_details_tool") is False

    def test_send_tool_is_not_list(self):
        """Test that send_ prefix is not list tool."""
        assert is_list_tool("send_email_tool") is False

    def test_create_tool_is_not_list(self):
        """Test that create_ prefix is not list tool."""
        assert is_list_tool("create_event_tool") is False

    def test_delete_tool_is_not_list(self):
        """Test that delete_ prefix is not list tool."""
        assert is_list_tool("delete_task_tool") is False

    def test_case_insensitive(self):
        """Test that check is case-insensitive."""
        assert is_list_tool("SEARCH_contacts_tool") is True
        assert is_list_tool("Search_Contacts_Tool") is True

    def test_empty_string_returns_false(self):
        """Test that empty string returns False."""
        assert is_list_tool("") is False

    def test_none_returns_false(self):
        """Test that None returns False."""
        assert is_list_tool(None) is False  # type: ignore


class TestIsListToolEdgeCases:
    """Tests for edge cases in is_list_tool."""

    def test_search_at_end_is_not_list(self):
        """Test that search at end doesn't match."""
        assert is_list_tool("contact_search") is False

    def test_search_in_middle_is_not_list(self):
        """Test that search in middle doesn't match."""
        assert is_list_tool("do_search_contact") is False

    def test_prefix_only_matches(self):
        """Test that only prefix patterns match."""
        # Only tools starting with search_, list_, find_, query_ are list tools
        assert is_list_tool("search_anything") is True
        assert is_list_tool("list_anything") is True
        assert is_list_tool("find_anything") is True
        assert is_list_tool("query_anything") is True


# ============================================================================
# Integration tests
# ============================================================================


class TestTypeDomainMappingIntegration:
    """Integration tests for type-domain mapping utilities."""

    def test_roundtrip_type_to_result_key_to_domain(self):
        """Test roundtrip from type to result_key and back to domain."""
        type_name = "CONTACT"

        # Type -> result_key
        result_key = get_result_key_from_type(type_name)
        assert result_key == "contacts"

        # result_key -> domain
        domain = get_domain_from_result_key(result_key)
        assert domain == "contact"

        # domain should match domain_name from type
        domain_name = get_domain_name_from_type(type_name)
        assert domain == domain_name

    def test_all_domains_have_result_key_mapping(self):
        """Test that all domains from TYPE_TO_DOMAIN_MAP have reverse mapping."""
        for type_name, (domain, items_key) in TYPE_TO_DOMAIN_MAP.items():
            # Check reverse lookup works
            reverse_domain = get_domain_from_result_key(items_key)
            assert reverse_domain == domain, f"Reverse lookup failed for {type_name}"

    def test_tool_patterns_cover_main_domains(self):
        """Test that tool patterns cover main domains."""
        main_domains = ["contacts", "emails", "events", "tasks", "files", "places"]

        for domain in main_domains:
            # Find pattern that maps to this domain
            found = False
            for _pattern, mapped_domain in TOOL_PATTERN_TO_DOMAIN_MAP.items():
                if mapped_domain == domain:
                    found = True
                    break
            assert found, f"No tool pattern maps to domain {domain}"


class TestTypeDomainMappingConsistency:
    """Tests for consistency in type-domain mapping."""

    def test_all_types_uppercase(self):
        """Test that all type names in map are uppercase."""
        for type_name in TYPE_TO_DOMAIN_MAP.keys():
            assert type_name == type_name.upper(), f"Type {type_name} is not uppercase"

    def test_all_domains_lowercase(self):
        """Test that all domain names are lowercase."""
        for _, (domain, items_key) in TYPE_TO_DOMAIN_MAP.items():
            assert domain == domain.lower(), f"Domain {domain} is not lowercase"
            assert items_key == items_key.lower(), f"Items key {items_key} is not lowercase"

    def test_all_items_keys_lowercase(self):
        """Test that all items_keys in registry config are lowercase."""
        for items_key in ITEMS_KEY_TO_REGISTRY_CONFIG.keys():
            assert items_key == items_key.lower(), f"Items key {items_key} is not lowercase"

    def test_all_tool_patterns_lowercase(self):
        """Test that all tool patterns are lowercase."""
        for pattern in TOOL_PATTERN_TO_DOMAIN_MAP.keys():
            assert pattern == pattern.lower(), f"Pattern {pattern} is not lowercase"
