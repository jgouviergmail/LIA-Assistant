"""Behavioral contracts of the envelope and invitation presentation."""

from html import unescape

import pytest

from src.core.constants import HTML_EVENT_VISIBLE_PARTICIPANTS
from src.core.i18n_cards import CardLabel, card_label
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import RenderContext, escape_html
from src.domains.agents.display.components.calendar_card import CalendarCard
from src.domains.agents.display.components.contact_card import ContactCard
from src.domains.agents.display.components.email_card import EmailCard
from src.domains.agents.display.components.email_parties import render_email_parties
from src.domains.agents.display.components.event_card import EventCard
from src.domains.agents.display.components.event_presentation import (
    event_response_status,
    render_event_attendees,
    render_event_date,
    render_event_response,
)
from src.domains.agents.display.components.task_item import TaskItem
from tests.helpers.card_people_cases import seven_guest_event, ten_email_messages

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "data,expected",
    [
        ({"name": "Name only"}, (False, False)),
        ({"emailAddresses": [{"value": "person@example.test"}]}, (True, False)),
        ({"addresses": [{"formattedValue": "18 Garden Street"}]}, (False, True)),
        ({"emailAddresses": [{"value": ""}], "phoneNumbers": [{}]}, (False, False)),
    ],
)
def test_contact_emits_only_populated_summary_sections(
    data: dict[str, object], expected: tuple[bool, bool]
) -> None:
    html = ContactCard().render(data, RenderContext(language="en"))
    assert ('class="lia-contact__directory"' in html) is expected[0]
    assert ('class="lia-contact__notes"' in html) is expected[1]


@pytest.mark.parametrize(
    "data,has_access",
    [
        ({}, False),
        ({"access_role": "unknown"}, False),
        ({"primary": True}, True),
        ({"access_role": "reader"}, True),
    ],
)
def test_calendar_emits_an_access_pocket_only_for_displayed_access_facts(
    data: dict[str, object], has_access: bool
) -> None:
    html = CalendarCard().render(data, RenderContext(language="en"))
    assert ('class="lia-calendar__access"' in html) is has_access
    assert 'class="lia-calendar__cover"' in html


def test_invitation_discloses_exactly_the_remaining_people_and_keeps_links() -> None:
    data = seven_guest_event()
    html = render_event_attendees(data["attendees"], RenderContext(language="en"))
    initial, remainder = html.split("<details", maxsplit=1)
    assert initial.count('<li class="lia-event__participant ') == HTML_EVENT_VISIBLE_PARTICIPANTS
    assert (
        remainder.count('<li class="lia-event__participant ') == 7 - HTML_EVENT_VISIBLE_PARTICIPANTS
    )
    assert f"({7 - HTML_EVENT_VISIBLE_PARTICIPANTS})" in remainder
    for index in range(1, 8):
        expected = initial if index <= HTML_EVENT_VISIBLE_PARTICIPANTS else remainder
        assert f'href="mailto:guest{index}@example.test"' in expected
        assert html.count(f'href="mailto:guest{index}@example.test"') == 1
    assert "lia-event__participant--unknown" in remainder
    assert '<details class="lia-details" open' not in html


@pytest.mark.parametrize("count", [0, 1, HTML_EVENT_VISIBLE_PARTICIPANTS])
def test_small_invitation_has_no_empty_or_unnecessary_disclosure(count: int) -> None:
    people = [{"email": f"guest{index}@example.test"} for index in range(count)]
    html = render_event_attendees(people, RenderContext(language="en"))
    assert "<details" not in html
    assert html.count('<li class="lia-event__participant ') == count


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_received_responses_are_named_in_the_readers_language(language: str) -> None:
    html = render_event_attendees(
        seven_guest_event()["attendees"], RenderContext(language=language)
    )
    keys: tuple[CardLabel, ...] = ("rsvp_accepted", "rsvp_declined", "rsvp_pending", "tentative")
    for key in keys:
        assert escape_html(card_label(key, language)) in html


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"organizer": {"self": True}},
        {"attendees": [{"self": True, "email": "person@example.test"}]},
        {"attendees": [{"email": "other@example.test", "responseStatus": "accepted"}]},
        {"attendees": [None, {}, "malformed"]},
    ],
)
def test_missing_own_response_never_implies_acceptance_or_pending(data: dict[str, object]) -> None:
    assert event_response_status(data) == ""
    assert render_event_response(data, RenderContext(language="en")) == ""
    assert EventCard()._get_response_status_class(data) == ""
    assert EventCard()._get_illus_for_status(data)[1] != "green"


def test_pending_invitation_is_not_accepted_even_when_event_is_confirmed() -> None:
    data = seven_guest_event()
    assert event_response_status(data) == "needsAction"
    assert EventCard()._get_illus_for_status(data)[1] == "amber"
    html = EventCard().render(data, RenderContext(language="en"))
    assert "EVENT_COMPLETE_DESCRIPTION" in html
    assert "https://video.example.test/garden" in html
    assert "https://calendar.example.test/invitation-seven-guests" in html
    assert "mailto:atelier@example.test" in html


def test_bad_participants_do_not_remove_valid_siblings_or_turn_text_into_markup() -> None:
    html = render_event_attendees(
        [None, {}, 0, {"displayName": "<script>name</script>", "email": "a@example.test"}],
        RenderContext(language="en"),
    )
    assert "&lt;script&gt;name&lt;/script&gt;" in html
    assert "<script>" not in html
    assert "1 participant" in html
    assert "lia-event__participant--accepted" not in html


@pytest.mark.parametrize(
    "value,expected",
    [
        ({"date": "2026-11-01"}, "<strong>1</strong>"),
        ({"dateTime": "2026-11-01T00:30:00Z"}, "<strong>31</strong>"),
        ({"date": "unreadable"}, ""),
        ({"dateTime": "unreadable"}, ""),
        (None, ""),
    ],
)
def test_tearoff_date_respects_civil_dates_and_the_display_timezone(
    value: object, expected: str
) -> None:
    html = render_event_date(value, RenderContext(language="en", timezone="America/New_York"))
    assert expected in html if expected else html == ""


def test_email_parties_preserve_quoted_names_and_unreadable_segments_without_fake_rsvp() -> None:
    html = render_email_parties(
        '"Martin, Alex" <alex@example.test>, unparsed person; bob@example.test'
    )
    assert 'href="mailto:alex@example.test"' in html
    assert "Martin, Alex" in html
    assert 'href="mailto:bob@example.test"' in html
    assert "unparsed person" in html
    assert 'href="mailto:unparsed' not in html
    assert "check_circle" not in html


def test_email_single_disclosure_contains_every_supplied_party_body_and_attachment() -> None:
    data = ten_email_messages()[0]
    data["bcc"] = "Bcc Person <bcc@example.test>"
    data["reply_to"] = "Reply Person <reply@example.test>"
    html = EmailCard().render(data, RenderContext(language="en"))
    initial, detail = html.split("<details", maxsplit=1)
    assert str(data["subject"]) in initial
    assert "sender1@example.test" in initial
    for fact in (
        "bcc@example.test",
        "reply@example.test",
        "EMAIL_COMPLETE_BODY_1",
        "Plan du jardin.pdf",
    ):
        assert fact in detail
    assert "<input" not in html


def test_long_provider_excerpt_is_kept_even_when_a_distinct_body_is_supplied() -> None:
    html = EmailCard().render(
        {"snippet": "Excerpt sentence. " * 30 + "EXCERPT_TAIL", "body": "DISTINCT_BODY"},
        RenderContext(language="en"),
    )
    assert "EXCERPT_TAIL" in html
    assert "DISTINCT_BODY" in html


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_unlisted_attachments_do_not_claim_an_invented_count(language: str) -> None:
    html = EmailCard().render(
        {"subject": "Metadata only", "hasAttachment": True}, RenderContext(language=language)
    )
    assert escape_html(card_label("attachments_unlisted", language)) in html


def test_task_checklist_is_visible_read_only_and_counts_only_renderable_steps() -> None:
    html = TaskItem().render(
        {
            "title": "Prepare the garden",
            "notes": "A long note. " * 40,
            "subtasks": [
                {"title": "Order seeds", "status": "completed"},
                None,
                {"status": "completed"},
                {"title": "Invite neighbours", "status": "needsAction"},
            ],
        },
        RenderContext(language="en"),
    )
    initial = html.split("<details", maxsplit=1)[0]
    assert "Order seeds" in initial and "Invite neighbours" in initial
    assert 'value="1" max="2"' in initial
    assert unescape(V3Messages.get_subtasks("en")) in unescape(initial)
    assert "<input" not in html
