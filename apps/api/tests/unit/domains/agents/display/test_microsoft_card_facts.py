"""Real Graph normalization and registry projections retain native user facts."""

import pytest
from langchain_core.messages import AIMessage

from src.core.field_names import FIELD_DISPLAY_ONLY
from src.core.time_utils import parse_provider_datetime
from src.domains.agents.data_registry.card_payload import card_payload, restore_display_fields
from src.domains.agents.data_registry.models import RegistryItem
from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.calendar_card import CalendarCard
from src.domains.agents.display.components.event_card import EventCard
from src.domains.agents.display.components.source_recurrence import render_source_recurrence
from src.domains.agents.display.components.task_item import TaskItem
from src.domains.agents.display.model_history import with_model_view
from src.domains.agents.tools.calendar_tools import ListCalendarsTool
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.connectors.clients.normalizers.microsoft_calendar_normalizer import (
    normalize_graph_calendar,
    normalize_graph_event,
)
from src.domains.connectors.clients.normalizers.microsoft_tasks_normalizer import (
    normalize_graph_task,
)
from src.infrastructure.llm.message_view import model_view_content

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "status,label",
    [
        ("inProgress", "In progress"),
        ("waitingOnOthers", "Waiting on others"),
        ("deferred", "Deferred"),
    ],
)
def test_native_task_status_and_categories_reach_the_card(status: str, label: str) -> None:
    normalized = normalize_graph_task(
        {
            "id": "task",
            "title": "Prepare visit",
            "status": status,
            "categories": ["Design", "Accessibility"],
            "isReminderOn": False,
            "hasAttachments": True,
            "createdDateTime": "2026-10-01T09:00:00Z",
        }
    )
    assert normalized["status"] == "needsAction"  # Existing execution alias remains compatible.
    markup = TaskItem().render(restore_display_fields(normalized), RenderContext(language="en"))
    for fact in (label, "Design", "Accessibility", "Reminder", "No", "Attachments", "Yes", "2026"):
        assert fact in markup
    assert FIELD_DISPLAY_ONLY in normalized


@pytest.mark.parametrize(
    "date_time,zone,expected",
    [
        ("2026-07-01T09:00:00.0000000", "Europe/Paris", "2026-07-01T07:00:00.000Z"),
        ("2026-01-01T09:00:00", "Europe/Paris", "2026-01-01T08:00:00.000Z"),
        ("2026-07-01T09:00:00.1234567+09:00", "Asia/Tokyo", "2026-07-01T00:00:00.123Z"),
    ],
)
def test_task_due_keeps_its_source_instant(date_time: str, zone: str, expected: str) -> None:
    normalized = normalize_graph_task(
        {"id": "task", "title": "Visit", "dueDateTime": {"dateTime": date_time, "timeZone": zone}}
    )
    assert normalized["due"] == expected


def test_unreadable_task_zone_is_not_silently_claimed_as_utc() -> None:
    normalized = normalize_graph_task(
        {
            "id": "task",
            "title": "Visit",
            "dueDateTime": {"dateTime": "2026-07-01T09:00:00", "timeZone": "Custom/Unknown"},
        }
    )
    assert normalized["due"] is None
    markup = TaskItem().render(restore_display_fields(normalized), RenderContext(language="en"))
    assert "Custom/Unknown" in markup
    assert "09:00:00" in markup


def test_task_html_notes_keep_paragraphs_and_drop_invisible_scripts() -> None:
    normalized = normalize_graph_task(
        {
            "id": "task",
            "title": "Visit",
            "body": {
                "contentType": "html",
                "content": "<p>First step</p><p>Final step &amp; access</p><script>hidden-script</script>",
            },
        }
    )
    assert normalized["notes"] == "First step\n\nFinal step & access"


def test_graph_event_recurrence_preserves_the_actual_days_interval_and_end() -> None:
    raw = {
        "id": "event",
        "subject": "Visit",
        "start": {"dateTime": "2026-10-05T09:00:00", "timeZone": "UTC"},
        "end": {"dateTime": "2026-10-05T10:00:00", "timeZone": "UTC"},
        "showAs": "free",
        "recurrence": {
            "pattern": {"type": "weekly", "interval": 2, "daysOfWeek": ["monday", "friday"]},
            "range": {"type": "numbered", "startDate": "2026-10-05", "numberOfOccurrences": 12},
        },
    }
    normalized = normalize_graph_event(raw)
    markup = EventCard().render(restore_display_fields(normalized), RenderContext(language="en"))
    for fact in ("Monday", "Friday", "2", "12", "Available"):
        assert fact in markup
    assert normalized[FIELD_DISPLAY_ONLY]["source_recurrence"] == raw["recurrence"]


def test_editable_graph_calendar_does_not_claim_ownership_in_its_card() -> None:
    normalized = normalize_graph_calendar({"id": "calendar", "name": "Team", "canEdit": True})
    assert normalized["accessRole"] == "writer"
    output = ListCalendarsTool().format_registry_response({"calendars": [normalized], "total": 1})
    item = next(iter(output.registry_updates.values()))
    markup = CalendarCard().render(card_payload(item), RenderContext(language="en"))
    assert "Can edit" in markup
    assert "Owner" not in markup


@pytest.mark.parametrize("text", ["2026-03-29T02:30:00", "2026-10-25T02:30:00"])
def test_naive_gap_or_ambiguous_provider_time_is_not_guessed(text: str) -> None:
    assert parse_provider_datetime({"dateTime": text, "timeZone": "Europe/Paris"}) is None


def test_graph_event_card_converts_the_stated_zone_and_keeps_all_day_civil_dates() -> None:
    raw = {
        "id": "event",
        "subject": "Visit",
        "start": {"dateTime": "2026-10-05T09:00:00", "timeZone": "Europe/Paris"},
        "end": {"dateTime": "2026-10-05T10:00:00", "timeZone": "Europe/Paris"},
    }
    markup = EventCard().render(
        restore_display_fields(normalize_graph_event(raw)),
        RenderContext(language="en", timezone="UTC"),
    )
    assert "7:00 AM" in markup and "8:00 AM" in markup
    raw.update(
        {
            "isAllDay": True,
            "start": {"dateTime": "2026-10-05T00:00:00", "timeZone": "Europe/Paris"},
            "end": {"dateTime": "2026-10-06T00:00:00", "timeZone": "Europe/Paris"},
        }
    )
    markup = EventCard().render(
        restore_display_fields(normalize_graph_event(raw)),
        RenderContext(language="en", timezone="UTC"),
    )
    assert "October 5" in markup


def test_recurrence_uses_its_own_zone_and_all_day_does_not_invent_a_clock() -> None:
    schedule = {
        "pattern": {"type": "weekly", "interval": 2, "daysOfWeek": ["monday", "friday"]},
        "range": {
            "type": "numbered",
            "startDate": "2026-10-05",
            "numberOfOccurrences": 12,
            "recurrenceTimeZone": "America/New_York",
        },
    }
    markup = render_source_recurrence(
        schedule,
        {"dateTime": "2026-10-05T09:00:00", "timeZone": "UTC"},
        RenderContext(language="en"),
    )
    assert "05:00" in markup
    assert "America/New_York" in markup
    markup = render_source_recurrence(
        schedule, {"date": "2026-10-05"}, RenderContext(language="en")
    )
    assert "Monday" in markup and "Friday" in markup
    assert "12" in markup
    assert "00:00" not in markup


def test_malformed_or_huge_recurrence_fields_cannot_dump_private_trees_or_unbounded_text() -> None:
    schedule = {
        "pattern": {"type": {"private": "raw-secret-tree"}, "daysOfWeek": ["monday"] * 20000},
        "range": {"type": "noEnd", "startDate": "2026-10-05"},
    }
    markup = render_source_recurrence(
        schedule, {"date": "2026-10-05"}, RenderContext(language="en")
    )
    assert "raw-secret-tree" not in markup
    assert len(markup) < 70000
    assert "omitted" in markup.lower()


def test_native_facts_survive_the_actual_registry_and_json_without_mutating_the_source() -> None:
    from copy import deepcopy

    class Output(ToolOutputMixin):
        tool_name = "native_fact_test"
        operation = "details"

    raw = {"id": "task", "title": "Visit", "status": "inProgress", "categories": ["Design"]}
    before = deepcopy(raw)
    normalized = normalize_graph_task(raw)
    output = Output().build_tasks_output([normalized], user_timezone="UTC", locale="en")
    item = next(iter(output.registry_updates.values()))
    assert raw == before
    assert FIELD_DISPLAY_ONLY not in item.payload
    assert "native_task" not in item.payload
    restored = RegistryItem.model_validate(item.model_dump(mode="json"))
    rendered = TaskItem().render(card_payload(restored), RenderContext(language="en"))
    assert "In progress" in rendered and "Design" in rendered


def test_recurrence_retains_anchor_and_week_start_even_when_human_summary_is_supported() -> None:
    schedule = {
        "pattern": {
            "type": "weekly",
            "interval": 2,
            "daysOfWeek": ["monday"],
            "firstDayOfWeek": "sunday",
        },
        "range": {"type": "noEnd", "startDate": "2026-10-01"},
    }
    markup = render_source_recurrence(
        schedule, {"date": "2026-10-05"}, RenderContext(language="en")
    )
    assert "October 1" in markup
    assert "Sunday" in markup


def test_date_only_is_not_a_provider_instant() -> None:
    assert parse_provider_datetime({"dateTime": "2026-10-05", "timeZone": "UTC"}) is None


def test_malformed_recurrence_scalars_do_not_crash_the_answer() -> None:
    schedule = {
        "pattern": {"type": "weekly", "interval": True, "daysOfWeek": [10**10000]},
        "range": {"type": "noEnd", "startDate": "2026-10-05", "recurrenceTimeZone": 10**10000},
    }
    markup = render_source_recurrence(
        schedule,
        {"dateTime": "2026-10-05T09:00:00", "timeZone": "UTC"},
        RenderContext(language="en"),
    )
    assert len(markup) < 70000
    assert "Every" not in markup


def test_native_event_availability_is_neither_duplicated_nor_invented() -> None:
    from src.domains.agents.display.components.source_details import event_native_details

    ctx = RenderContext(language="en")
    assert (
        len(
            event_native_details(
                {"native_event": {"showAs": "free"}, "transparency": "transparent"}, ctx
            )
        )
        == 1
    )
    data = restore_display_fields(normalize_graph_event({"id": "event", "subject": "Visit"}))
    assert not event_native_details(data, ctx)


def test_actual_event_output_preserves_the_provider_instant_before_rendering() -> None:
    class Output(ToolOutputMixin):
        tool_name = "native_fact_test"
        operation = "details"

    event = normalize_graph_event(
        {
            "id": "event",
            "subject": "Visit",
            "start": {"dateTime": "2026-10-05T09:00:00", "timeZone": "Europe/Paris"},
            "end": {"dateTime": "2026-10-05T10:00:00", "timeZone": "Europe/Paris"},
        }
    )
    output = Output().build_events_output([event], user_timezone="UTC", locale="en")
    item = next(iter(output.registry_updates.values()))
    assert item.payload["start"]["dateTime"] == "2026-10-05T07:00:00+00:00"
    assert item.payload["date"] == "2026-10-05T07:00:00+00:00"
    markup = EventCard().render(
        card_payload(item), RenderContext(language="en", timezone="Europe/Paris")
    )
    assert "9:00 AM" in markup and "10:00 AM" in markup


def test_actual_all_day_registry_recurrence_never_exposes_synthetic_clock() -> None:
    class Output(ToolOutputMixin):
        tool_name = "native_fact_test"
        operation = "details"

    event = normalize_graph_event(
        {
            "id": "event",
            "subject": "Visit",
            "isAllDay": True,
            "start": {"dateTime": "2026-10-05T00:00:00", "timeZone": "Europe/Paris"},
            "end": {"dateTime": "2026-10-06T00:00:00", "timeZone": "Europe/Paris"},
            "recurrence": {
                "pattern": {"type": "weekly", "interval": 1, "daysOfWeek": ["monday"]},
                "range": {"type": "noEnd", "startDate": "2026-10-05"},
            },
        }
    )
    output = Output().build_events_output([event], user_timezone="UTC", locale="en")
    data = card_payload(next(iter(output.registry_updates.values())))
    markup = render_source_recurrence(
        data["source_recurrence"], data["start"], RenderContext(language="en")
    )
    assert "Monday" in markup and "00:00" not in markup
    card = EventCard().render(data, RenderContext(language="en", timezone="UTC"))
    assert "All day" in card and "12:00 AM" not in card
    west = EventCard().render(data, RenderContext(language="en", timezone="America/Los_Angeles"))
    assert "October 5" in west and "October 4" not in west


@pytest.mark.parametrize("zone", ["Unknown/Zone", "W. Europe Standard Time"])
def test_event_conversion_retains_unknown_source_without_inventing_an_instant(zone: str) -> None:
    from src.core.time_utils import convert_event_dates_in_payload

    edge = {"dateTime": "2026-10-05T09:00:00", "timeZone": zone, "formatted": "STALE"}
    convert_event_dates_in_payload({"start": edge}, "UTC", "en")
    assert edge == {"dateTime": "2026-10-05T09:00:00", "timeZone": zone}


def test_unknown_provider_zone_cannot_become_a_cross_domain_instant() -> None:
    class Output(ToolOutputMixin):
        tool_name = "native_fact_test"
        operation = "details"

    event = normalize_graph_event(
        {
            "id": "event",
            "subject": "Visit",
            "start": {"dateTime": "2026-10-05T09:00:00", "timeZone": "Unknown/Zone"},
            "end": {"dateTime": "2026-10-05T10:00:00", "timeZone": "Unknown/Zone"},
        }
    )
    item = next(iter(Output().build_events_output([event], locale="en").registry_updates.values()))
    assert "date" not in item.payload
    markup = EventCard().render(card_payload(item), RenderContext(language="en"))
    assert "Unknown/Zone" in markup and "2026-10-05T09:00:00" in markup


def test_actual_registry_snapshot_retains_the_complete_graph_schedule_without_fake_rrule() -> None:
    schedule = {
        "pattern": {"type": "absoluteMonthly", "interval": 2, "dayOfMonth": 15},
        "range": {"type": "numbered", "startDate": "2026-10-15", "numberOfOccurrences": 12},
    }
    normalized = normalize_graph_event({"id": "event", "recurrence": schedule})
    assert normalized["recurrence"] == []
    assert normalized["recurrence_pattern"] == schedule
    message = with_model_view(
        AIMessage(content="UI"),
        "A recurring visit",
        {"event": {"type": "EVENT", "payload": normalized}},
    )
    view = model_view_content(message)
    assert view is not None and '"interval": 2' in view and '"numberOfOccurrences": 12' in view
    assert "RRULE:FREQ=ABSOLUTEMONTHLY" not in view
