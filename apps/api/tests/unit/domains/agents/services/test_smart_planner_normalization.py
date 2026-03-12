"""
Unit tests for SmartPlannerService tool name normalization.

Ensures that tool names are correctly normalized to match unified v2.0 naming convention.
All search/list/details tools are now unified under get_*_tool.

Also tests for for_each misplacement auto-correction.
"""

from unittest.mock import patch

import pytest

from src.domains.agents.services.smart_planner_service import SmartPlannerService


class TestToolNameNormalization:
    """Tests for _normalize_tool_name method (unified v2.0 architecture)."""

    @pytest.fixture
    def planner(self):
        """Create SmartPlannerService instance."""
        return SmartPlannerService()

    # =========================================================================
    # Basic normalization: add _tool suffix if missing
    # =========================================================================

    def test_adds_tool_suffix_when_missing(self, planner):
        """Tool name without _tool suffix gets it added and normalized to unified."""
        result = planner._normalize_tool_name("search_events", "calendar")
        assert result == "get_events_tool"  # Unified v2.0

    def test_preserves_unknown_tool_suffix_when_present(self, planner):
        """Unknown tool name with _tool suffix is unchanged."""
        result = planner._normalize_tool_name("unknown_tool", "custom")
        assert result == "unknown_tool"

    def test_empty_string_returns_empty(self, planner):
        """Empty tool name returns empty string."""
        result = planner._normalize_tool_name("", "calendar")
        assert result == ""

    # =========================================================================
    # Calendar domain corrections (unified v2.0)
    # =========================================================================

    def test_corrects_list_events_to_get_events(self, planner):
        """LLM often says 'list_events' but correct is 'get_events_tool' (unified)."""
        result = planner._normalize_tool_name("list_events", "calendar")
        assert result == "get_events_tool"

    def test_corrects_find_events_to_get_events(self, planner):
        """'find_events' should become 'get_events_tool' (unified)."""
        result = planner._normalize_tool_name("find_events", "calendar")
        assert result == "get_events_tool"

    def test_corrects_search_events_to_get_events(self, planner):
        """'search_events' should become 'get_events_tool' (unified)."""
        result = planner._normalize_tool_name("search_events", "calendar")
        assert result == "get_events_tool"

    # =========================================================================
    # Contacts domain corrections (unified v2.0)
    # =========================================================================

    def test_corrects_find_contacts_to_get_contacts(self, planner):
        """'find_contacts' should become 'get_contacts_tool' (unified)."""
        result = planner._normalize_tool_name("find_contacts", "contacts")
        assert result == "get_contacts_tool"

    def test_corrects_search_contacts_to_get_contacts(self, planner):
        """'search_contacts' should become 'get_contacts_tool' (unified)."""
        result = planner._normalize_tool_name("search_contacts", "contacts")
        assert result == "get_contacts_tool"

    # =========================================================================
    # Emails domain corrections (unified v2.0)
    # =========================================================================

    def test_corrects_find_emails_to_get_emails(self, planner):
        """'find_emails' should become 'get_emails_tool' (unified)."""
        result = planner._normalize_tool_name("find_emails", "emails")
        assert result == "get_emails_tool"

    # =========================================================================
    # Tasks domain corrections (unified v2.0)
    # =========================================================================

    def test_corrects_find_tasks_to_get_tasks(self, planner):
        """'find_tasks' should become 'get_tasks_tool' (unified)."""
        result = planner._normalize_tool_name("find_tasks", "tasks")
        assert result == "get_tasks_tool"

    # =========================================================================
    # Drive domain corrections (unified v2.0)
    # =========================================================================

    def test_corrects_find_files_to_get_files(self, planner):
        """'find_files' should become 'get_files_tool' (unified)."""
        result = planner._normalize_tool_name("find_files", "drive")
        assert result == "get_files_tool"

    # =========================================================================
    # Places domain corrections (unified v2.0)
    # =========================================================================

    def test_corrects_find_places_to_get_places(self, planner):
        """'find_places' should become 'get_places_tool' (unified)."""
        result = planner._normalize_tool_name("find_places", "places")
        assert result == "get_places_tool"

    # =========================================================================
    # Unknown tools pass through with suffix added
    # =========================================================================

    def test_unknown_tool_gets_suffix_added(self, planner):
        """Unknown tool names just get _tool suffix."""
        result = planner._normalize_tool_name("some_custom_action", "custom")
        assert result == "some_custom_action_tool"


class TestUnifiedToolNormalization:
    """Tests verifying unified v2.0 tool names are correctly normalized.

    Note: Normalization only applies to tools WITHOUT _tool suffix.
    Tools already ending in _tool are returned as-is (lines 578-580 in smart_planner_service.py).
    Corrections are only applied when suffix is added by the normalizer.
    """

    @pytest.fixture
    def planner(self):
        """Create SmartPlannerService instance."""
        return SmartPlannerService()

    @pytest.mark.parametrize(
        "input_tool,domain,expected",
        [
            # Calendar - tools WITHOUT suffix get normalized
            ("search_events", "calendar", "get_events_tool"),
            ("list_events", "calendar", "get_events_tool"),
            ("find_events", "calendar", "get_events_tool"),
            # Contacts
            ("search_contacts", "contacts", "get_contacts_tool"),
            ("list_contacts", "contacts", "get_contacts_tool"),
            # Emails
            ("search_emails", "emails", "get_emails_tool"),
            ("list_emails", "emails", "get_emails_tool"),
            # Tasks
            ("search_tasks", "tasks", "get_tasks_tool"),
            ("list_tasks", "tasks", "get_tasks_tool"),
            # Drive
            ("search_files", "drive", "get_files_tool"),
            # Places
            ("search_places", "places", "get_places_tool"),
        ],
    )
    def test_unified_tool_normalization(self, planner, input_tool, domain, expected):
        """Tools without _tool suffix should be normalized to unified get_* tools."""
        result = planner._normalize_tool_name(input_tool, domain)
        assert result == expected, f"{input_tool} should normalize to {expected}"

    @pytest.mark.parametrize(
        "input_tool,domain",
        [
            # Tools WITH _tool suffix are returned as-is (no correction applied)
            ("search_events_tool", "calendar"),
            ("list_events_tool", "calendar"),
            ("search_contacts_tool", "contacts"),
            ("get_events_tool", "calendar"),  # Already correct
            ("get_contacts_tool", "contacts"),  # Already correct
        ],
    )
    def test_tools_with_suffix_returned_as_is(self, planner, input_tool, domain):
        """Tools already ending in _tool are returned unchanged."""
        result = planner._normalize_tool_name(input_tool, domain)
        assert result == input_tool, f"{input_tool} should be returned as-is"


class TestForEachMisplacementCorrection:
    """Tests for for_each attributes incorrectly placed in parameters.

    Bug: LLMs sometimes put for_each inside parameters instead of as step attribute.
    This causes tools to receive 'for_each' as unexpected keyword argument.
    The _build_plan method should auto-correct this by extracting these attributes.
    """

    @pytest.fixture
    def planner(self):
        """Create SmartPlannerService instance."""
        return SmartPlannerService()

    @pytest.fixture
    def mock_intelligence(self):
        """Create mock QueryIntelligence."""
        from unittest.mock import MagicMock

        from src.domains.agents.analysis.query_intelligence import UserGoal

        intelligence = MagicMock()
        intelligence.primary_domain = "weather"
        intelligence.domains = ["weather", "event"]
        intelligence.original_query = "weather for each event"
        intelligence.english_enriched_query = "weather for each event"
        intelligence.user_goal = UserGoal.FIND_INFORMATION  # Use actual Enum
        return intelligence

    @pytest.fixture
    def mock_config(self):
        """Create mock RunnableConfig."""
        return {
            "configurable": {
                "user_id": "test_user",
                "thread_id": "test_thread",
                "run_id": "test_run",
            }
        }

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings with for_each configuration."""
        from unittest.mock import MagicMock

        settings = MagicMock()
        settings.for_each_max_default = 10
        settings.for_each_max_hard_limit = 100
        settings.planner_auto_correct_for_each_max = True
        settings.planner_auto_correct_for_each_misplacement = True
        return settings

    @patch("src.core.config.get_settings")
    def test_extracts_for_each_from_parameters(
        self, mock_get_settings, planner, mock_intelligence, mock_config, mock_settings
    ):
        """for_each placed in parameters should be extracted to step attribute."""
        mock_get_settings.return_value = mock_settings

        plan_data = {
            "steps": [
                {
                    "id": "step_1",
                    "tool_name": "get_events_tool",
                    "parameters": {},
                },
                {
                    "id": "step_2",
                    "tool_name": "get_current_weather_tool",
                    # WRONG: LLM put for_each inside parameters
                    "parameters": {
                        "location": "$item.location",
                        "for_each": "$steps.step_1.events",
                    },
                    "depends_on": ["step_1"],
                },
            ]
        }

        plan = planner._build_plan(plan_data, mock_intelligence, mock_config)

        # Verify step_2 has for_each as attribute, not in parameters
        step_2 = plan.steps[1]
        assert (
            step_2.for_each == "$steps.step_1.events"
        ), "for_each should be extracted as step attribute"
        assert "for_each" not in step_2.parameters, "for_each should NOT remain in parameters"
        assert step_2.parameters.get("location") == "$item.location", "Other params preserved"

    @patch("src.core.config.get_settings")
    def test_ignores_for_each_list_in_parameters(
        self, mock_get_settings, planner, mock_intelligence, mock_config, mock_settings
    ):
        """for_each as list (not string ref) in parameters should be ignored."""
        mock_get_settings.return_value = mock_settings

        plan_data = {
            "steps": [
                {
                    "id": "step_1",
                    "tool_name": "get_current_weather_tool",
                    # WRONG: LLM put for_each as list inside parameters
                    "parameters": {
                        "location": "Paris",
                        "for_each": [
                            {"id": "event1"},
                            {"id": "event2"},
                        ],  # Invalid: list, not string
                    },
                },
            ]
        }

        plan = planner._build_plan(plan_data, mock_intelligence, mock_config)

        # for_each should be None (ignored because it's not a string reference)
        step = plan.steps[0]
        assert step.for_each is None, "for_each as list should be ignored"
        assert "for_each" not in step.parameters, "for_each should be removed from parameters"

    @patch("src.core.config.get_settings")
    def test_extracts_all_for_each_attributes(
        self, mock_get_settings, planner, mock_intelligence, mock_config, mock_settings
    ):
        """All for_each-related attributes should be extracted from parameters."""
        mock_get_settings.return_value = mock_settings

        plan_data = {
            "steps": [
                {
                    "id": "step_1",
                    "tool_name": "send_email_tool",
                    "parameters": {
                        "to": "$item.email",
                        "for_each": "$steps.get_contacts.contacts",
                        "for_each_max": 5,
                        "on_item_error": "stop",
                        "delay_between_items_ms": 100,
                    },
                },
            ]
        }

        plan = planner._build_plan(plan_data, mock_intelligence, mock_config)

        step = plan.steps[0]
        # All for_each attributes should be extracted
        assert step.for_each == "$steps.get_contacts.contacts"
        assert step.for_each_max == 5
        assert step.on_item_error == "stop"
        assert step.delay_between_items_ms == 100
        # None should remain in parameters
        assert "for_each" not in step.parameters
        assert "for_each_max" not in step.parameters
        assert "on_item_error" not in step.parameters
        assert "delay_between_items_ms" not in step.parameters
        # Regular param should be preserved
        assert step.parameters.get("to") == "$item.email"

    @patch("src.core.config.get_settings")
    def test_step_level_for_each_takes_precedence(
        self, mock_get_settings, planner, mock_intelligence, mock_config, mock_settings
    ):
        """Step-level for_each should take precedence over misplaced parameters."""
        mock_get_settings.return_value = mock_settings

        plan_data = {
            "steps": [
                {
                    "id": "step_1",
                    "tool_name": "send_email_tool",
                    # Correct: for_each at step level
                    "for_each": "$steps.get_contacts.contacts",
                    "parameters": {
                        "to": "$item.email",
                        # WRONG: also in parameters (should be ignored)
                        "for_each": "$steps.something_else.items",
                    },
                },
            ]
        }

        plan = planner._build_plan(plan_data, mock_intelligence, mock_config)

        step = plan.steps[0]
        # Step-level value should win
        assert step.for_each == "$steps.get_contacts.contacts"
        assert "for_each" not in step.parameters

    @patch("src.core.config.get_settings")
    def test_for_each_always_extracted_from_parameters(
        self, mock_get_settings, planner, mock_intelligence, mock_config, mock_settings
    ):
        """for_each is always extracted from parameters (misplacement auto-correction is always on)."""
        mock_get_settings.return_value = mock_settings

        plan_data = {
            "steps": [
                {
                    "id": "step_1",
                    "tool_name": "get_current_weather_tool",
                    "parameters": {
                        "location": "$item.location",
                        "for_each": "$steps.step_1.events",  # Misplaced in parameters
                    },
                },
            ]
        }

        plan = planner._build_plan(plan_data, mock_intelligence, mock_config)

        step = plan.steps[0]
        # for_each should always be extracted as step attribute
        assert step.for_each == "$steps.step_1.events", "for_each should be extracted"
        assert "for_each" not in step.parameters, "for_each should be removed from parameters"
