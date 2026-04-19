"""Tests for the ``structured_data`` contract across tool output helpers.

Validates:

1. ``ToolOutputMixin._build_items_structured_data`` produces a flat, queryable
   payload aligned with the INTELLIPLANNER B+ contract.
2. Every ``build_*_output`` helper exposes its domain entities and relevant
   search metadata via ``structured_data`` so that deterministic plans can
   chain downstream steps via ``$steps.<step_id>.<plural_key>``.
3. The shared ``create_tool_formatter`` factory honours the same contract.

These tests are the single source of truth for the helper-level contract used
by the orchestration layer (parallel executor) and skill scripts.
"""

from __future__ import annotations

from typing import Any

from src.domains.agents.data_registry.models import RegistryItemType
from src.domains.agents.tools.mixins import ToolOutputMixin, create_tool_formatter


class _HelperAccessor(ToolOutputMixin):
    """Concrete subclass used only to access the mixin helpers in tests."""

    tool_name = "test_helper"
    operation = "test"


class TestBuildItemsStructuredData:
    """Tests for :meth:`ToolOutputMixin._build_items_structured_data`."""

    def test_exposes_items_and_count(self) -> None:
        """Items are exposed under the plural key with a matching count."""
        result = ToolOutputMixin._build_items_structured_data(
            items=[{"id": "a"}, {"id": "b"}],
            plural_key="widgets",
        )

        assert result["widgets"] == [{"id": "a"}, {"id": "b"}]
        assert result["count"] == 2

    def test_none_metadata_values_are_filtered(self) -> None:
        """``None`` metadata values are stripped so the payload stays compact."""
        result = ToolOutputMixin._build_items_structured_data(
            items=[],
            plural_key="widgets",
            query="foo",
            optional=None,
        )

        assert result == {"widgets": [], "count": 0, "query": "foo"}

    def test_items_are_shallow_copied(self) -> None:
        """The snapshot is stable even when the caller later mutates the source."""
        item: dict[str, Any] = {"id": "x"}
        items = [item]
        result = ToolOutputMixin._build_items_structured_data(
            items=items,
            plural_key="widgets",
        )
        item["id"] = "mutated"

        assert result["widgets"][0]["id"] == "x"


class TestBuildContactsOutput:
    """Tests for :meth:`ToolOutputMixin.build_contacts_output`."""

    def test_contacts_exposed_with_search_metadata(self) -> None:
        helper = _HelperAccessor()
        output = helper.build_contacts_output(
            contacts=[
                {"resourceName": "people/c1", "names": [{"displayName": "Alice"}]},
                {"resourceName": "people/c2", "names": [{"displayName": "Bob"}]},
            ],
            query="alice",
            operation="search",
            from_cache=True,
        )

        assert output.structured_data["count"] == 2
        assert len(output.structured_data["contacts"]) == 2
        assert output.structured_data["query"] == "alice"
        assert output.structured_data["operation"] == "search"
        assert output.structured_data["from_cache"] is True


class TestBuildEmailsOutput:
    """Tests for :meth:`ToolOutputMixin.build_emails_output`."""

    def test_emails_exposed_with_timezone(self) -> None:
        helper = _HelperAccessor()
        output = helper.build_emails_output(
            emails=[{"id": "m1", "subject": "Hello"}],
            query="hello",
            user_timezone="Europe/Paris",
        )

        assert output.structured_data["count"] == 1
        assert output.structured_data["emails"][0]["id"] == "m1"
        assert output.structured_data["user_timezone"] == "Europe/Paris"
        assert output.structured_data["query"] == "hello"


class TestBuildEventsOutput:
    """Tests for :meth:`ToolOutputMixin.build_events_output`."""

    def test_events_exposed_with_time_range(self) -> None:
        helper = _HelperAccessor()
        output = helper.build_events_output(
            events=[
                {
                    "id": "e1",
                    "summary": "Meeting",
                    "start": {"dateTime": "2026-04-20T10:00:00+00:00"},
                    "end": {"dateTime": "2026-04-20T11:00:00+00:00"},
                }
            ],
            time_min="2026-04-20T00:00:00+00:00",
            time_max="2026-04-20T23:59:59+00:00",
            calendar_id="primary",
            user_timezone="UTC",
        )

        assert output.structured_data["count"] == 1
        assert output.structured_data["events"][0]["id"] == "e1"
        assert output.structured_data["time_min"] == "2026-04-20T00:00:00+00:00"
        assert output.structured_data["time_max"] == "2026-04-20T23:59:59+00:00"
        assert output.structured_data["calendar_id"] == "primary"


class TestBuildTasksOutput:
    """Tests for :meth:`ToolOutputMixin.build_tasks_output`."""

    def test_tasks_exposed_with_list_id(self) -> None:
        helper = _HelperAccessor()
        output = helper.build_tasks_output(
            tasks=[{"id": "t1", "title": "Buy bread"}],
            task_list_id="list-42",
        )

        assert output.structured_data["tasks"][0]["id"] == "t1"
        assert output.structured_data["task_list_id"] == "list-42"
        assert output.structured_data["count"] == 1


class TestBuildFilesOutput:
    """Tests for :meth:`ToolOutputMixin.build_files_output`."""

    def test_files_exposed_with_folder(self) -> None:
        helper = _HelperAccessor()
        output = helper.build_files_output(
            files=[{"id": "f1", "name": "report.pdf"}],
            query="report",
            folder_id="folder-1",
        )

        assert output.structured_data["files"][0]["id"] == "f1"
        assert output.structured_data["folder_id"] == "folder-1"
        assert output.structured_data["query"] == "report"


class TestBuildPlacesOutput:
    """Tests for :meth:`ToolOutputMixin.build_places_output`."""

    def test_places_exposed_with_geo_context(self) -> None:
        helper = _HelperAccessor()
        output = helper.build_places_output(
            places=[{"id": "p1", "displayName": {"text": "Café Paris"}}],
            query="café",
            operation="nearby",
            center={"lat": 48.85, "lng": 2.35},
            radius=500,
        )

        assert output.structured_data["places"][0]["id"] == "p1"
        assert output.structured_data["operation"] == "nearby"
        assert output.structured_data["center"] == {"lat": 48.85, "lng": 2.35}
        assert output.structured_data["radius"] == 500


class TestBuildWeatherOutput:
    """Tests for :meth:`ToolOutputMixin.build_weather_output`."""

    def test_weather_exposed_as_single_item_list(self) -> None:
        helper = _HelperAccessor()
        payload: dict[str, Any] = {"name": "Paris", "main": {"temp": 15}}
        output = helper.build_weather_output(
            weather_data=payload,
            location="Paris",
        )

        assert output.structured_data["count"] == 1
        assert output.structured_data["weathers"][0]["name"] == "Paris"
        assert output.structured_data["location"] == "Paris"


class TestBuildStandardOutput:
    """Tests for :meth:`ToolOutputMixin.build_standard_output`."""

    def test_standard_output_uses_registry_plural_key(self) -> None:
        helper = _HelperAccessor()
        output = helper.build_standard_output(
            items=[{"id": "c1", "name": "Alice"}, {"id": "c2", "name": "Bob"}],
            item_type=RegistryItemType.CONTACT,
            source="test_source",
            unique_key_field="id",
            preview_field="name",
            domain="contacts",
        )

        assert output.structured_data["count"] == 2
        assert len(output.structured_data["contacts"]) == 2
        assert output.structured_data["domain"] == "contacts"

    def test_standard_output_accepts_explicit_plural_key(self) -> None:
        helper = _HelperAccessor()
        output = helper.build_standard_output(
            items=[{"id": "n1"}],
            item_type=RegistryItemType.NOTE,
            source="test_source",
            unique_key_field="id",
            plural_key="custom_notes",
        )

        assert "custom_notes" in output.structured_data
        assert output.structured_data["count"] == 1


class TestCreateToolFormatter:
    """Tests for :func:`create_tool_formatter`."""

    def test_factory_exposes_items_and_query(self) -> None:
        formatter = create_tool_formatter(
            item_type=RegistryItemType.FILE,
            source="test_drive",
            unique_key_field="id",
            preview_field="name",
            domain="files",
        )

        output = formatter(
            [{"id": "f1", "name": "report.pdf"}, {"id": "f2", "name": "notes.txt"}],
            query="report",
        )

        assert output.structured_data["count"] == 2
        assert len(output.structured_data["files"]) == 2
        assert output.structured_data["query"] == "report"
        assert output.structured_data["source"] == "test_drive"
