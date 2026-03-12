"""
INTELLIPLANNER B+ - Tests for StandardToolOutput structured_data.

Validates:
1. get_step_output() returns structured_data when populated
2. Fallback extracts from registry_updates grouped by type
3. Empty output returns summary fallback
"""

from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
)
from src.domains.agents.tools.output import REGISTRY_TYPE_TO_KEY, StandardToolOutput


class TestStandardToolOutputStructuredData:
    """Tests for INTELLIPLANNER B+ structured_data functionality."""

    def test_get_step_output_with_structured_data(self):
        """structured_data has priority over registry_updates."""
        output = StandardToolOutput(
            summary_for_llm="Found 2 calendars",
            structured_data={"calendars": [{"id": "cal1"}, {"id": "cal2"}], "count": 2},
        )
        result = output.get_step_output()

        assert result == {"calendars": [{"id": "cal1"}, {"id": "cal2"}], "count": 2}
        assert result["calendars"][0]["id"] == "cal1"

    def test_get_step_output_fallback_from_registry_updates(self):
        """Fallback extracts payloads grouped by type from registry_updates."""
        output = StandardToolOutput(
            summary_for_llm="Found 2 contacts",
            registry_updates={
                "contact_abc": RegistryItem(
                    id="contact_abc",
                    type=RegistryItemType.CONTACT,
                    payload={"name": "John", "email": "john@test.com"},
                    meta=RegistryItemMeta(source="test"),
                ),
                "contact_def": RegistryItem(
                    id="contact_def",
                    type=RegistryItemType.CONTACT,
                    payload={"name": "Jane", "email": "jane@test.com"},
                    meta=RegistryItemMeta(source="test"),
                ),
            },
        )
        result = output.get_step_output()

        assert "contacts" in result
        assert len(result["contacts"]) == 2
        assert result["count"] == 2
        # Payloads are extracted
        names = {c["name"] for c in result["contacts"]}
        assert names == {"John", "Jane"}

    def test_get_step_output_fallback_calendar_type(self):
        """Fallback correctly maps CALENDAR type to 'calendars' key."""
        output = StandardToolOutput(
            summary_for_llm="Found 1 calendar",
            registry_updates={
                "cal_abc": RegistryItem(
                    id="cal_abc",
                    type=RegistryItemType.CALENDAR,
                    payload={"id": "cal_abc", "summary": "Primary"},
                    meta=RegistryItemMeta(source="google_calendar"),
                ),
            },
        )
        result = output.get_step_output()

        assert "calendars" in result
        assert result["calendars"][0]["id"] == "cal_abc"
        assert result["calendars"][0]["summary"] == "Primary"
        assert result["count"] == 1

    def test_get_step_output_empty_output(self):
        """Empty output returns summary fallback."""
        output = StandardToolOutput(summary_for_llm="No results found")
        result = output.get_step_output()

        assert result == {"summary": "No results found", "count": 0}

    def test_get_step_output_mixed_types(self):
        """Fallback groups items by their types."""
        output = StandardToolOutput(
            summary_for_llm="Found mixed items",
            registry_updates={
                "contact_1": RegistryItem(
                    id="contact_1",
                    type=RegistryItemType.CONTACT,
                    payload={"name": "John"},
                    meta=RegistryItemMeta(source="test"),
                ),
                "email_1": RegistryItem(
                    id="email_1",
                    type=RegistryItemType.EMAIL,
                    payload={"subject": "Hello"},
                    meta=RegistryItemMeta(source="test"),
                ),
            },
        )
        result = output.get_step_output()

        assert "contacts" in result
        assert "emails" in result
        assert len(result["contacts"]) == 1
        assert len(result["emails"]) == 1
        assert result["count"] == 2

    def test_registry_type_to_key_mapping(self):
        """Verify REGISTRY_TYPE_TO_KEY mapping covers common types."""
        expected_mappings = {
            RegistryItemType.CONTACT: "contacts",
            RegistryItemType.EMAIL: "emails",
            RegistryItemType.EVENT: "events",
            RegistryItemType.CALENDAR: "calendars",
            RegistryItemType.TASK: "tasks",
            RegistryItemType.FILE: "files",
            RegistryItemType.PLACE: "places",
            RegistryItemType.WEATHER: "weathers",  # Plural for consistency (v3.2)
            RegistryItemType.DRAFT: "drafts",
        }

        for item_type, expected_key in expected_mappings.items():
            assert (
                REGISTRY_TYPE_TO_KEY.get(item_type) == expected_key
            ), f"Mapping for {item_type} should be '{expected_key}'"

    def test_structured_data_priority_over_registry(self):
        """structured_data takes priority even when registry_updates populated."""
        output = StandardToolOutput(
            summary_for_llm="Test priority",
            structured_data={"custom_key": "custom_value"},
            registry_updates={
                "item_1": RegistryItem(
                    id="item_1",
                    type=RegistryItemType.CONTACT,
                    payload={"name": "Should not appear"},
                    meta=RegistryItemMeta(source="test"),
                ),
            },
        )
        result = output.get_step_output()

        # Should return structured_data, not registry extraction
        assert result == {"custom_key": "custom_value"}
        assert "contacts" not in result
