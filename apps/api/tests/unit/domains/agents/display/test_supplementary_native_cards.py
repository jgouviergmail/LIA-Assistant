"""Native producer facts reach read-only cards without a second provider request."""

import pytest

from src.domains.agents.data_registry.card_payload import card_payload
from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.calendar_card import CalendarCard
from src.domains.agents.display.components.event_card import EventCard
from src.domains.agents.display.components.snapshot_cards import HueLightCard, TicketCard
from src.domains.agents.tools.calendar_tools import ListCalendarsTool
from src.domains.agents.tools.hue_tools import ListHueLightsTool

pytestmark = pytest.mark.unit


def test_ticket_display_facts_survive_json_without_becoming_recurring_model_context() -> None:
    from langchain_core.messages import AIMessage

    from src.domains.agents.data_registry.models import RegistryItem
    from src.domains.agents.display.model_history import with_model_view
    from src.domains.agents.workboard.context import ticket_registry_items
    from src.infrastructure.llm.message_view import MODEL_VIEW_KEY

    details = {
        "description": "DISPLAY_ONLY_DESCRIPTION",
        "comments": [{"body": "DISPLAY_ONLY_COMMENT"}],
    }
    original = ticket_registry_items(
        [{"id": "ticket", "title": "Garden", "status": "todo"}],
        tool_name="get_ticket_tool",
        display_by_id={"ticket": details},
    )["ticket"]
    details["comments"][0]["body"] = "MUTATED_AFTER_PROJECTION"
    archived = RegistryItem.model_validate_json(original.model_dump_json())
    markup = TicketCard().render(card_payload(archived), RenderContext(language="en"))
    assert "DISPLAY_ONLY_COMMENT" in markup and "MUTATED_AFTER_PROJECTION" not in markup
    message = with_model_view(AIMessage(content=markup), "Your garden.", {"ticket": archived})
    semantic = message.additional_kwargs[MODEL_VIEW_KEY]["content"]
    assert "Garden" in semantic
    assert "DISPLAY_ONLY" not in semantic and "lia-card" not in semantic


def test_hue_projection_cannot_copy_nested_provider_credentials_or_mutate_with_input() -> None:
    from src.domains.agents.display.components.light_details import hue_display_fields

    raw = {
        "color": {"xy": {"x": 0.3, "y": 0.4, "api_key": "SECRET"}},
        "color_temperature": {
            "mirek": 250,
            "mirek_valid": True,
            "mirek_schema": {"mirek_minimum": 153, "mirek_maximum": 500, "api_key": "SECRET"},
        },
    }
    snapshot = hue_display_fields(raw)
    raw["color"]["xy"]["x"] = 0.9
    assert snapshot["color"]["xy"]["x"] == 0.3
    assert "SECRET" not in str(snapshot)


@pytest.mark.parametrize("kind", [None, [], {}, 0])
def test_malformed_join_point_does_not_hide_other_received_join_points(kind: object) -> None:
    markup = EventCard().render(
        {
            "summary": "Meet",
            "conferenceData": {
                "entryPoints": [
                    {"entryPointType": kind},
                    {"entryPointType": "video", "uri": "https://meet.example.test/valid"},
                ]
            },
        },
        RenderContext(language="en"),
    )
    assert "https://meet.example.test/valid" in markup


def test_ticket_complete_text_zero_cost_and_usage_without_raw_execution_secrets() -> None:
    markup = TicketCard().render(
        {
            "title": "Visit",
            "description": "First sentence. " * 40 + "LAST_DESCRIPTION",
            "children": [{"title": "Step one", "status": "done", "priority": "urgent"}],
            "comments": [{"author": "peer", "body": "<img src=x onerror=alert(1)> LAST_COMMENT"}],
            "last_run": {
                "outcome": "skipped_quota",
                "cost_eur": 0,
                "tokens_in": 0,
                "tokens_out": 12,
                "error": "Authorization: SECRET_DO_NOT_DISPLAY",
            },
        },
        RenderContext(language="en"),
    )
    for fact in (
        "LAST_DESCRIPTION",
        "LAST_COMMENT",
        "Step one",
        "quota reached",
        "0 €",
        "Input tokens: 0",
        "Output tokens: 12",
    ):
        assert fact in markup
    assert "SECRET_DO_NOT_DISPLAY" not in markup and "<img src=x" not in markup


@pytest.mark.parametrize(
    "mirek",
    [1e-320, 10**5000, float("nan"), True, -1],
    ids=["sub-mirek", "huge-int", "nan", "bool", "negative"],
)
def test_invalid_hue_measurement_does_not_break_a_card(mirek: object) -> None:
    markup = HueLightCard().render(
        {"name": "Desk", "color_temperature": {"mirek": mirek, "mirek_valid": True}},
        RenderContext(language="en"),
    )
    assert "Unavailable" in markup
    assert " K " not in markup


def test_explicitly_disabled_event_reminders_do_not_look_like_missing_data() -> None:
    markup = EventCard().render(
        {"summary": "Meet", "reminders": {"useDefault": False}}, RenderContext(language="en")
    )
    assert "No reminders" in markup


def test_invalid_reminders_do_not_invent_default_popup_or_zero_minutes() -> None:
    markup = EventCard().render(
        {
            "summary": "Meet",
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"minutes": 10**5000},
                    {"minutes": 40321, "method": "popup"},
                    {"minutes": True, "method": "email"},
                ],
            },
        },
        RenderContext(language="en"),
    )
    assert "Notification" not in markup and "Email" not in markup
    assert "No reminders" not in markup


def test_huge_untrusted_integer_is_not_a_display_string_or_a_render_failure() -> None:
    from src.domains.agents.display.values import scalar_text

    assert scalar_text(10**5000) == ""


def test_join_metadata_excludes_provider_identifiers_and_untrusted_html() -> None:
    markup = EventCard().render(
        {
            "summary": "Meet",
            "conferenceData": {
                "conferenceId": "DO_NOT_DISPLAY_ID",
                "signature": "DO_NOT_DISPLAY_SIGNATURE",
                "notes": "<script>DO_NOT_DISPLAY_SCRIPT</script><p>Dial in</p>",
                "entryPoints": [
                    {
                        "entryPointType": "sip",
                        "uri": "sip:meeting@example.test",
                        "label": "SIP",
                        "accessCode": "<b>1234</b>",
                    },
                    None,
                ],
            },
        },
        RenderContext(language="en"),
    )
    assert "DO_NOT_DISPLAY" not in markup and "<b>1234</b>" not in markup
    assert "sip:meeting@example.test" in markup and "Dial in" in markup


def test_native_hue_measurements_survive_the_registry_with_zero_brightness() -> None:
    output = ListHueLightsTool(
        tool_name="list_hue_lights", operation="list"
    ).format_registry_response(
        {
            "data": {
                "lights": [
                    {
                        "id": "light",
                        "metadata": {"name": "Desk"},
                        "on": {"on": True},
                        "dimming": {"brightness": 0},
                        "color": {"xy": {"x": 0.3, "y": 0.4}},
                        "color_temperature": {"mirek": 250, "mirek_valid": True},
                    }
                ]
            }
        }
    )
    item = next(iter(output.registry_updates.values()))
    markup = HueLightCard().render(card_payload(item), RenderContext(language="en"))
    assert 'value="0"' in markup and "<meter" in markup
    assert "4000 K" in markup and "0.3" in markup and "0.4" in markup
    assert "color_temperature" not in item.payload


def test_hue_invalid_temperature_cannot_be_presented_as_a_current_white_temperature() -> None:
    markup = HueLightCard().render(
        {"name": "Desk", "color_temperature": {"mirek": 250, "mirek_valid": False}},
        RenderContext(language="en"),
    )
    assert "4000 K" not in markup
    assert "Unavailable" in markup


def test_google_calendar_defaults_and_selection_reach_the_native_card() -> None:
    output = ListCalendarsTool().format_registry_response(
        {
            "calendars": [
                {
                    "id": "cal",
                    "summary": "Original calendar",
                    "summaryOverride": "My garden",
                    "accessRole": "writer",
                    "selected": False,
                    "hidden": True,
                    "defaultReminders": [
                        {"method": "email", "minutes": 0},
                        {"method": "popup", "minutes": 10},
                    ],
                }
            ],
            "total": 1,
        }
    )
    markup = CalendarCard().render(
        card_payload(next(iter(output.registry_updates.values()))), RenderContext(language="en")
    )
    for fact in (
        "My garden",
        "Original calendar",
        "Email",
        "Notification",
        "10",
        "Hidden",
        "Selected",
        "No",
        "Yes",
    ):
        assert fact in markup


def test_every_supplied_event_join_point_and_access_code_remains_available() -> None:
    markup = EventCard().render(
        {
            "summary": "Meet",
            "conferenceData": {
                "entryPoints": [
                    {"entryPointType": "video", "uri": "https://meet.example.test/first"},
                    {"entryPointType": "video", "uri": "https://meet.example.test/second"},
                    {
                        "entryPointType": "phone",
                        "uri": "tel:+33123456789",
                        "label": "+33 1 23 45 67 89",
                        "pin": "123456",
                    },
                    {"entryPointType": "more", "uri": "javascript:alert(1)", "label": "Unsafe"},
                ]
            },
        },
        RenderContext(language="en"),
    )
    for fact in (
        "https://meet.example.test/first",
        "https://meet.example.test/second",
        "+33 1 23 45 67 89",
        "123456",
    ):
        assert fact in markup
    assert "javascript:" not in markup
