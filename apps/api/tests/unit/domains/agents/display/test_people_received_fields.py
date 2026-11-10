"""Received people-card facts survive native normalization and registry persistence."""

from datetime import timedelta
from html import unescape
from uuid import UUID

import pytest

from src.core.i18n_cards import card_label
from src.core.i18n_sms import SMS_CARD_LABELS
from src.core.time_utils import now_in_timezone
from src.domains.agents.data_registry.card_payload import card_payload
from src.domains.agents.data_registry.models import RegistryItem
from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.calendar_card import CalendarCard
from src.domains.agents.display.components.contact_card import ContactCard
from src.domains.agents.display.components.email_card import EmailCard
from src.domains.agents.display.components.event_card import EventCard
from src.domains.agents.display.components.event_presentation import event_response_status
from src.domains.agents.display.components.reminder_card import ReminderCard
from src.domains.agents.display.components.sms_card import SmsCard
from src.domains.agents.display.components.task_item import TaskItem
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.connectors.clients.normalizers.contacts_normalizer import normalize_vcard
from src.domains.connectors.clients.normalizers.microsoft_calendar_normalizer import (
    normalize_graph_event,
)
from src.domains.connectors.clients.normalizers.microsoft_contacts_normalizer import (
    normalize_graph_contact,
)
from src.domains.connectors.clients.normalizers.microsoft_tasks_normalizer import (
    normalize_graph_task,
)

pytestmark = pytest.mark.unit


def _payload(output: UnifiedToolOutput) -> dict[str, object]:
    item = next(iter(output.registry_updates.values()))
    result = card_payload(RegistryItem.model_validate_json(item.model_dump_json()))
    assert result is not None
    return result


@pytest.mark.parametrize("provider", ["google", "apple", "microsoft"])
def test_received_contact_websites_reach_the_card_from_each_provider(provider: str) -> None:
    url = "https://studio.example.test/about?team=design&lang=en"
    if provider == "microsoft":
        source = normalize_graph_contact(
            {"id": "person", "displayName": "Alex", "businessHomePage": url}
        )
    elif provider == "apple":
        source = normalize_vcard(
            f"BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Alex\r\nURL:{url}\r\nEND:VCARD\r\n",
            "https://contacts.example.test/alex.vcf",
        )
    else:
        source = {
            "resourceName": "people/alex",
            "names": [{"displayName": "Alex"}],
            "urls": [{"value": url}],
        }
    html = ContactCard().render(
        _payload(ToolOutputMixin().build_contacts_output([source])), RenderContext(language="en")
    )
    assert url in unescape(html)
    assert f'href="{url}"' in unescape(html)


def test_contact_website_labels_and_unsafe_urls_remain_literal_text() -> None:
    html = ContactCard().render(
        {
            "name": "Alex",
            "urls": [
                {"value": "https://studio.example.test", "type": "Portfolio <2027>"},
                {"value": "javascript:bad()"},
            ],
        },
        RenderContext(language="en"),
    )
    assert "Portfolio &lt;2027&gt;" in html
    assert "javascript:bad()" in html
    assert 'href="javascript:' not in html


def test_contact_structured_name_and_address_survive_without_formatted_aliases() -> None:
    html = ContactCard().render(
        {
            "names": [
                {
                    "honorificPrefix": "Dr",
                    "givenName": "Alex",
                    "middleName": "River",
                    "familyName": "Martin",
                    "honorificSuffix": "Jr",
                }
            ],
            "addresses": [
                {
                    "streetAddress": "8 Garden Street",
                    "city": "Bristol",
                    "postalCode": "BS1 1AA",
                    "country": "United Kingdom",
                }
            ],
        },
        RenderContext(language="en"),
    )
    for fact in (
        "Dr Alex River Martin Jr",
        "8 Garden Street",
        "Bristol",
        "BS1 1AA",
        "United Kingdom",
    ):
        assert fact in html


@pytest.mark.parametrize(
    "provider,due,zone,day",
    [
        ("google", "2027-11-03T00:00:00.000Z", "America/Los_Angeles", "November 3, 2027"),
        ("google", "2027-11-03T00:00:00.000Z", "Pacific/Kiritimati", "November 3, 2027"),
        ("microsoft", "2027-11-02T23:00:00.000Z", "Europe/Paris", "November 3, 2027"),
        ("microsoft", "2027-11-03T08:00:00.000Z", "America/Los_Angeles", "November 3, 2027"),
    ],
)
def test_task_due_uses_the_provider_civil_day(provider: str, due: str, zone: str, day: str) -> None:
    source = {"id": "task", "title": "Visit", "due": due, "_provider": provider}
    data = _payload(ToolOutputMixin().build_tasks_output([source], user_timezone=zone, locale="en"))
    assert day in TaskItem().render(data, RenderContext(language="en", timezone=zone))


@pytest.mark.parametrize("day_offset,overdue", [(-1, True), (0, False), (1, False)])
def test_task_due_today_is_not_overdue_until_the_local_day_ends(
    day_offset: int, overdue: bool
) -> None:
    zone = "Pacific/Kiritimati"
    due = (now_in_timezone(zone).date() + timedelta(days=day_offset)).isoformat()
    html = TaskItem().render(
        {"title": "Visit", "due": due + "T00:00:00Z"}, RenderContext(language="en", timezone=zone)
    )
    assert ("lia-task--overdue" in html) is overdue


def test_native_todo_steps_preserve_checked_and_unchecked_after_json_roundtrip() -> None:
    source = normalize_graph_task(
        {
            "id": "task",
            "title": "Visit",
            "checklistItems": [
                {"id": "one", "displayName": "Book train", "isChecked": True},
                {"id": "two", "displayName": "Pack bag", "isChecked": False},
            ],
        }
    )
    data = _payload(ToolOutputMixin().build_tasks_output([source], locale="en"))
    html = TaskItem().render(data, RenderContext(language="en"))
    assert "<s>Book train</s>" in html
    assert "Pack bag" in html and "<s>Pack bag</s>" not in html
    assert 'value="1" max="2"' in html


def test_missing_step_completion_is_not_counted_as_known_pending() -> None:
    html = TaskItem().render(
        {"title": "Visit", "steps": [{"title": "Unknown state"}]}, RenderContext(language="en")
    )
    assert "Unknown state" in html
    assert "<progress" not in html
    assert "<s>" not in html


def test_completed_task_keeps_its_due_priority_and_human_source_link() -> None:
    html = TaskItem().render(
        {
            "title": "Visit",
            "status": "completed",
            "completed": "2027-11-04T10:00:00Z",
            "due": "2027-11-03T00:00:00Z",
            "importance": "high",
            "webViewLink": "https://tasks.example.test/visit",
            "selfLink": "https://api.example.test/task",
        },
        RenderContext(language="en", timezone="UTC"),
    )
    assert "November 3, 2027" in html and "November 4, 2027" in html
    assert "High" in html
    assert 'href="https://tasks.example.test/visit"' in html


@pytest.mark.parametrize(
    "response,expected",
    [
        ("accepted", "accepted"),
        ("declined", "declined"),
        ("tentativelyAccepted", "tentative"),
        ("notResponded", "needsAction"),
    ],
)
def test_microsoft_own_response_reaches_invitation_without_a_self_attendee(
    response: str, expected: str
) -> None:
    source = normalize_graph_event(
        {"id": "event", "subject": "Visit", "responseStatus": {"response": response}}
    )
    data = _payload(ToolOutputMixin().build_events_output([source], locale="en"))
    assert event_response_status(data) == expected


def test_event_keeps_overnight_end_date_year_and_known_source_timezone() -> None:
    html = EventCard().render(
        {
            "summary": "Overnight visit",
            "start": {"dateTime": "2027-12-31T23:30:00Z"},
            "end": {"dateTime": "2028-01-01T01:00:00Z"},
            "ownZone": "Europe/London",
        },
        RenderContext(language="en", timezone="UTC"),
    )
    details = html.split("<details", 1)[1]
    assert "December 31, 2027" in details and "January 1, 2028" in details
    assert "Europe/London" in details


@pytest.mark.parametrize("zone", ["America/Los_Angeles", "Pacific/Kiritimati"])
def test_all_day_period_has_its_last_included_civil_day(zone: str) -> None:
    html = EventCard().render(
        {"summary": "Retreat", "start": {"date": "2027-11-03"}, "end": {"date": "2027-11-06"}},
        RenderContext(language="en", timezone=zone),
    )
    details = html.split("<details", 1)[1]
    assert "November 3, 2027" in details and "November 5, 2027" in details
    assert "November 6" not in details and "12:00" not in details


def test_event_keeps_native_zero_minute_reminder() -> None:
    source = normalize_graph_event(
        {"id": "event", "subject": "Visit", "isReminderOn": True, "reminderMinutesBeforeStart": 0}
    )
    data = _payload(ToolOutputMixin().build_events_output([source], locale="en"))
    html = EventCard().render(data, RenderContext(language="en"))
    assert "At event time" in html


def test_event_keeps_received_participant_context_without_changing_rsvp() -> None:
    html = EventCard().render(
        {
            "summary": "Visit",
            "attendees": [
                {
                    "email": "room@example.test",
                    "optional": False,
                    "resource": True,
                    "additionalGuests": 0,
                    "comment": "Access <side door>",
                },
                {"email": "alex@example.test", "optional": True},
            ],
        },
        RenderContext(language="en"),
    )
    for label in (
        "required_participant",
        "resource_participant",
        "additional_guests",
        "optional_participant",
    ):
        assert card_label(label, "en") in html
    assert "Access &lt;side door&gt;" in html
    assert "lia-event__participant--accepted" not in html


def test_event_without_received_details_has_no_empty_disclosure() -> None:
    html = EventCard().render({"summary": "Title only"}, RenderContext(language="en"))
    assert "<details" not in html


def test_reminder_with_raw_dates_still_shows_its_received_schedule() -> None:
    html = ReminderCard().render(
        {
            "content": "Call Alex",
            "trigger_at": "2027-11-03T10:00:00Z",
            "created_at": "2027-11-01T08:00:00Z",
            "schedule_timezone": "Europe/London",
        },
        RenderContext(language="en", timezone="UTC"),
    )
    for fact in ("November 3, 2027", "November 1, 2027", "Europe/London"):
        assert fact in html


def test_final_sms_body_page_still_states_that_the_message_is_partial() -> None:
    html = SmsCard().render(
        {
            "id": str(UUID(int=8)),
            "sender": "+44123456",
            "display_name": "Alex",
            "body": "LAST RECEIVED PAGE",
            "body_offset": 50,
            "next_body_offset": None,
            "received_at": "2027-11-03T10:00:00Z",
            "date_kind": "received",
        },
        RenderContext(language="en"),
    )
    assert "LAST RECEIVED PAGE" in html
    assert SMS_CARD_LABELS["en"]["more"] in html


@pytest.mark.parametrize("language", ["en", "fr", "de", "es", "it", "zh-CN"])
def test_explicit_email_folder_and_star_states_are_distinct_from_importance(language: str) -> None:
    html = EmailCard().render(
        {"subject": "Source states", "labelIds": ["SENT", "TRASH", "SPAM", "STARRED"]},
        RenderContext(language=language),
    )
    for label in ("email_sent", "email_trash", "email_spam", "email_starred"):
        assert card_label(label, language) in html
    assert "lia-email--important" not in html


def test_partial_email_digest_keeps_received_points_without_fabricating_a_gist() -> None:
    html = EmailCard().render(
        {
            "subject": "Partial digest",
            "key_points": ["POINT_WITHOUT_GIST"],
            "actions": ["ACTION_WITHOUT_GIST"],
        },
        RenderContext(language="en"),
    )
    assert "POINT_WITHOUT_GIST" in html and "ACTION_WITHOUT_GIST" in html


def test_calendar_accepts_native_access_role_without_overriding_explicit_unknown() -> None:
    assert "Owner" in CalendarCard().render(
        {"summary": "Native", "accessRole": "owner"}, RenderContext(language="en")
    )
    assert "Owner" not in CalendarCard().render(
        {"summary": "Unknown", "accessRole": "owner", "access_role": None},
        RenderContext(language="en"),
    )


@pytest.mark.parametrize("end", ["2027-11-03", "2027-11-02", "malformed"])
def test_incoherent_all_day_end_is_named_unavailable_without_an_invented_period(end: str) -> None:
    html = EventCard().render(
        {"summary": "Incoherent source", "start": {"date": "2027-11-03"}, "end": {"date": end}},
        RenderContext(language="en"),
    )
    assert card_label("unavailable", "en") in html
    assert end in html


def test_google_lifecycle_dates_remain_available_without_native_provider_metadata() -> None:
    event = EventCard().render(
        {"summary": "Visit", "created": "2027-10-01T10:00:00Z", "updated": "2027-11-02T11:00:00Z"},
        RenderContext(language="en", timezone="UTC"),
    )
    assert "October 1, 2027" in event and "November 2, 2027" in event
    task = TaskItem().render(
        {"title": "Prepare visit", "updated": "2027-11-02T11:00:00Z"},
        RenderContext(language="en", timezone="UTC"),
    )
    assert "November 2, 2027" in task


def test_malformed_checklist_state_does_not_drop_valid_received_siblings() -> None:
    html = TaskItem().render(
        {
            "title": "Prepare visit",
            "subtasks": [
                {"title": "Unresolved", "status": {}},
                {"title": "Confirmed done", "status": "completed"},
            ],
        },
        RenderContext(language="en"),
    )
    assert "Unresolved" in html and "<s>Confirmed done</s>" in html
    assert "<progress" not in html


def test_standalone_received_meeting_link_remains_reachable() -> None:
    html = EventCard().render(
        {"summary": "Visit", "hangoutLink": "https://meet.google.com/abc-defg-hij"},
        RenderContext(language="en"),
    )
    assert 'href="https://meet.google.com/abc-defg-hij"' in html


@pytest.mark.parametrize("attendees", [[], [{"email": "guest@example.test"}]])
def test_provider_omitted_participants_are_explicit_even_without_a_received_name(
    attendees: list[dict[str, str]],
) -> None:
    ctx = RenderContext(language="en")
    html = EventCard().render(
        {"summary": "Partial invitation", "attendees": attendees, "attendeesOmitted": True}, ctx
    )
    assert card_label("participants_partial", "en") in html
    complete = EventCard().render({"summary": "Complete", "attendees": attendees}, ctx)
    assert card_label("participants_partial", "en") not in complete


@pytest.mark.parametrize("language", ["en", "fr", "de", "es", "it", "zh-CN"])
def test_reminder_browser_reference_retains_complete_source_fields(language: str) -> None:
    from tests.helpers.card_reminder_reference import reminder_reference_domains

    records = reminder_reference_domains(language)["reminders"]["reminders"]
    assert isinstance(records, list)
    record = records[0]
    html = ReminderCard().render(record, RenderContext(language=language, timezone="Europe/Paris"))
    for key in (
        "content",
        "trigger_at_formatted",
        "created_at_formatted",
        "schedule_human",
        "schedule_timezone",
    ):
        assert record[key] in unescape(html)
