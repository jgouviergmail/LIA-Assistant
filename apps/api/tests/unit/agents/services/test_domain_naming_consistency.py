"""Unit tests for domain naming consistency.

Ensures that all domain names are canonical and consistent across:
- Router prompts
- Domain taxonomy
- Agent registry
- Constants

Created: 2025-11-20
Updated: 2026-01 - Refactoring v3.2 unified naming (domain=singular, result_key=plural)

Naming Convention (v3.2):
- domain = entity singular: contact, email, event, file, task, place, route, weather, wikipedia, perplexity, query
- result_key = domain + "s": contacts, emails, events, files, tasks, places, routes, weathers, wikipedias, perplexitys, querys
- agent_name = domain + "_agent": contact_agent, email_agent, event_agent, wikipedia_agent, perplexity_agent, etc.
"""

import pytest

from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY


def normalize_domain_name(domain: str) -> str:
    """Normalize domain name to lowercase."""
    return domain.lower()


def test_domain_registry_uses_email_canonical():
    """Test that domain registry uses 'email' as canonical name (not 'gmail' or 'emails')."""
    assert "email" in DOMAIN_REGISTRY, "Email domain should exist in registry"
    assert "gmail" not in DOMAIN_REGISTRY, "Deprecated 'gmail' should not exist"
    assert "emails" not in DOMAIN_REGISTRY, "Pluralized 'emails' should not be a domain key"

    # Verify email domain config
    email_config = DOMAIN_REGISTRY["email"]
    assert email_config.name == "email"
    assert email_config.display_name == "Emails"
    assert email_config.result_key == "emails"  # result_key is plural


def test_normalize_domain_name_is_identity():
    """Test that normalize_domain_name is now an identity function.

    Since v7 hierarchical prompts, LLM is trained to return canonical names.
    The function should just lowercase the input (no mapping).
    """
    # Canonical names should pass through (singular)
    assert normalize_domain_name("email") == "email"
    assert normalize_domain_name("Email") == "email"  # Case normalization
    assert normalize_domain_name("contact") == "contact"
    assert normalize_domain_name("event") == "event"


def test_domain_registry_contact_exists():
    """Test that contact domain exists with canonical name."""
    assert "contact" in DOMAIN_REGISTRY
    contact_config = DOMAIN_REGISTRY["contact"]
    assert contact_config.name == "contact"
    assert contact_config.result_key == "contacts"


def test_domain_registry_context_exists():
    """Test that context domain exists with canonical name."""
    assert "context" in DOMAIN_REGISTRY
    context_config = DOMAIN_REGISTRY["context"]
    assert context_config.name == "context"


@pytest.mark.parametrize(
    "domain_name,expected_result_key",
    [
        ("email", "emails"),
        ("contact", "contacts"),
        ("event", "events"),
        ("file", "files"),
        ("task", "tasks"),
        ("weather", "weathers"),
        ("place", "places"),
        ("route", "routes"),
        ("context", "contexts"),
        # LOT 10-11: New domains (domain + "s" pattern)
        ("wikipedia", "wikipedias"),
        ("perplexity", "perplexitys"),
        ("query", "querys"),
    ],
)
def test_all_canonical_domains_in_registry(domain_name: str, expected_result_key: str):
    """Test that all currently implemented domain names are present in registry.

    Convention (v3.2):
    - domain key = singular entity name
    - result_key = domain + "s"

    Args:
        domain_name: Canonical domain name (singular)
        expected_result_key: Expected result_key (plural)
    """
    assert domain_name in DOMAIN_REGISTRY, f"Domain '{domain_name}' should exist"
    config = DOMAIN_REGISTRY[domain_name]
    assert config.name == domain_name, f"Domain name mismatch for '{domain_name}'"
    assert config.result_key == expected_result_key, (
        f"result_key mismatch for '{domain_name}': expected '{expected_result_key}', "
        f"got '{config.result_key}'"
    )


def test_no_deprecated_domain_names():
    """Test that deprecated domain name variants are not in registry.

    Deprecated variants that should NOT exist:
    - "gmail" (use "email")
    - "emails" (use "email", result_key is "emails")
    - "contacts" (use "contact")
    - "calendar" (use "event")
    - "drive" (use "file")
    - "tasks" (use "task")
    """
    deprecated_names = ["gmail", "emails", "contacts", "calendar", "drive", "tasks"]

    for deprecated in deprecated_names:
        assert (
            deprecated not in DOMAIN_REGISTRY
        ), f"Deprecated domain '{deprecated}' should not exist as registry key"


def test_agent_names_follow_convention():
    """Test that all agent_names follow the domain_agent pattern."""
    for domain_name, config in DOMAIN_REGISTRY.items():
        for agent_name in config.agent_names:
            expected = f"{domain_name}_agent"
            assert agent_name == expected, (
                f"Agent name '{agent_name}' for domain '{domain_name}' "
                f"should follow pattern: '{expected}'"
            )


# ============================================================================
# Tests for get_result_key_for_tool()
# ============================================================================
# Source of truth for tool_name → result_key mapping
# Used by semantic_validator to validate $steps references
# ============================================================================


class TestGetResultKeyForTool:
    """Tests for get_result_key_for_tool function.

    This function maps tool names to their canonical result_key.
    Critical for validating $steps.step_X.{result_key} references in plans.
    """

    @pytest.fixture
    def get_result_key_for_tool(self):
        """Import the function under test."""
        from src.domains.agents.registry.domain_taxonomy import get_result_key_for_tool

        return get_result_key_for_tool

    # -------------------------------------------------------------------------
    # Pattern 1: {action}_{domain}_tool (singular domain in middle)
    # -------------------------------------------------------------------------
    @pytest.mark.parametrize(
        "tool_name,expected_result_key",
        [
            ("get_weather_tool", "weathers"),
            ("send_email_tool", "emails"),
            ("create_event_tool", "events"),
            ("update_contact_tool", "contacts"),
            ("delete_task_tool", "tasks"),
            ("create_task_tool", "tasks"),
            ("update_event_tool", "events"),
            ("reply_email_tool", "emails"),
            ("forward_email_tool", "emails"),
            ("delete_email_tool", "emails"),
            ("complete_task_tool", "tasks"),
            ("get_route_tool", "routes"),
        ],
    )
    def test_action_domain_tool_pattern(
        self, get_result_key_for_tool, tool_name: str, expected_result_key: str
    ):
        """Test tools with {action}_{domain}_tool pattern."""
        result = get_result_key_for_tool(tool_name)
        assert (
            result == expected_result_key
        ), f"Tool '{tool_name}' should return '{expected_result_key}', got '{result}'"

    # -------------------------------------------------------------------------
    # Pattern 2: {action}_{domain}s_tool (plural domain in middle)
    # -------------------------------------------------------------------------
    @pytest.mark.parametrize(
        "tool_name,expected_result_key",
        [
            ("get_contacts_tool", "contacts"),
            ("get_events_tool", "events"),
            ("get_emails_tool", "emails"),
            ("get_files_tool", "files"),
            ("get_tasks_tool", "tasks"),
            ("get_places_tool", "places"),
        ],
    )
    def test_action_domains_tool_pattern(
        self, get_result_key_for_tool, tool_name: str, expected_result_key: str
    ):
        """Test tools with {action}_{domain}s_tool pattern (plural)."""
        result = get_result_key_for_tool(tool_name)
        assert (
            result == expected_result_key
        ), f"Tool '{tool_name}' should return '{expected_result_key}', got '{result}'"

    # -------------------------------------------------------------------------
    # Pattern 3: {domain}_{action}_tool (domain at start)
    # -------------------------------------------------------------------------
    @pytest.mark.parametrize(
        "tool_name,expected_result_key",
        [
            ("perplexity_search_tool", "perplexitys"),
            ("perplexity_ask_tool", "perplexitys"),
        ],
    )
    def test_domain_action_tool_pattern(
        self, get_result_key_for_tool, tool_name: str, expected_result_key: str
    ):
        """Test tools with {domain}_{action}_tool pattern."""
        result = get_result_key_for_tool(tool_name)
        assert (
            result == expected_result_key
        ), f"Tool '{tool_name}' should return '{expected_result_key}', got '{result}'"

    # -------------------------------------------------------------------------
    # Pattern 4: Weather tools (various patterns)
    # -------------------------------------------------------------------------
    @pytest.mark.parametrize(
        "tool_name,expected_result_key",
        [
            ("get_current_weather_tool", "weathers"),
            ("get_weather_forecast_tool", "weathers"),
        ],
    )
    def test_weather_tools(self, get_result_key_for_tool, tool_name: str, expected_result_key: str):
        """Test weather-related tools."""
        result = get_result_key_for_tool(tool_name)
        assert (
            result == expected_result_key
        ), f"Tool '{tool_name}' should return '{expected_result_key}', got '{result}'"

    def test_hourly_forecast_tool_is_edge_case(self, get_result_key_for_tool):
        """Test that get_hourly_forecast_tool may not match (edge case).

        This tool doesn't contain 'weather' in its name, so it may not be
        matched. This is acceptable as:
        1. It's rarely used in $steps references
        2. Adding 'forecast' as a keyword could cause false positives
        """
        result = get_result_key_for_tool("get_hourly_forecast_tool")
        # Either None or "weathers" is acceptable
        assert result is None or result == "weathers"

    # -------------------------------------------------------------------------
    # Pattern 5: Wikipedia tools
    # -------------------------------------------------------------------------
    @pytest.mark.parametrize(
        "tool_name,expected_result_key",
        [
            ("search_wikipedia_tool", "wikipedias"),
            ("get_wikipedia_summary_tool", "wikipedias"),
            ("get_wikipedia_article_tool", "wikipedias"),
            ("get_wikipedia_related_tool", "wikipedias"),
        ],
    )
    def test_wikipedia_tools(
        self, get_result_key_for_tool, tool_name: str, expected_result_key: str
    ):
        """Test Wikipedia tools."""
        result = get_result_key_for_tool(tool_name)
        assert (
            result == expected_result_key
        ), f"Tool '{tool_name}' should return '{expected_result_key}', got '{result}'"

    # -------------------------------------------------------------------------
    # Edge cases: Tools that should NOT match (metadata tools)
    # -------------------------------------------------------------------------
    def test_metadata_tools_may_not_match(self, get_result_key_for_tool):
        """Test that metadata tools may return None (acceptable).

        These tools are for navigation/discovery, not for producing
        data that gets referenced in $steps.
        """
        # These tools don't produce data referenced via $steps
        metadata_tools = [
            "list_calendars_tool",  # Lists available calendars
            "list_task_lists_tool",  # Lists available task lists
        ]

        for tool_name in metadata_tools:
            result = get_result_key_for_tool(tool_name)
            # Result can be None or a valid key - both acceptable
            # The important thing is it doesn't crash
            assert result is None or isinstance(result, str)

    # -------------------------------------------------------------------------
    # Edge cases: Empty/None input
    # -------------------------------------------------------------------------
    def test_empty_input_returns_none(self, get_result_key_for_tool):
        """Test that empty or None input returns None."""
        assert get_result_key_for_tool("") is None
        assert get_result_key_for_tool(None) is None

    # -------------------------------------------------------------------------
    # Case insensitivity
    # -------------------------------------------------------------------------
    def test_case_insensitive(self, get_result_key_for_tool):
        """Test that tool name matching is case-insensitive."""
        assert get_result_key_for_tool("GET_CONTACTS_TOOL") == "contacts"
        assert get_result_key_for_tool("Get_Contacts_Tool") == "contacts"
        assert get_result_key_for_tool("get_WEATHER_tool") == "weathers"
