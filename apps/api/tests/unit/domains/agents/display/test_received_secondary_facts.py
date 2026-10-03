"""Secondary native facts remain visible without adding provider fetches."""

import pytest

from src.domains.agents.data_registry.card_payload import card_payload
from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.calendar_card import CalendarCard
from src.domains.agents.display.components.contact_card import ContactCard
from src.domains.agents.tools.calendar_tools import ListCalendarsTool
from tests.helpers.card_microsoft_reference import NativeReferenceOutput

pytestmark = pytest.mark.unit


def test_partial_employment_dates_are_text_and_zero_equivalent_is_preserved() -> None:
    markup = ContactCard().render(
        {
            "names": [{"displayName": "Garden keeper"}],
            "organizations": [
                {
                    "name": "Garden",
                    "startDate": {"year": 2021},
                    "endDate": {"month": 2, "day": 29},
                    "fullTimeEquivalentMillipercent": 0,
                }
            ],
        },
        RenderContext(language="en"),
    )
    assert "2021" in markup and "--02-29" in markup
    assert 'datetime="2021"' not in markup and 'datetime="--02-29"' not in markup
    assert "Full-time equivalent: 0%" in markup


@pytest.mark.parametrize(
    "value,expected",
    [
        ({"year": 2021}, "2021"),
        ({"year": 2021, "month": 4}, "2021-04"),
        ({"month": 2, "day": 29}, "--02-29"),
        ({"year": 2021, "month": 2, "day": 29}, ""),
        ({"year": True, "month": 4}, ""),
        ({"year": 10**5000}, ""),
        ({"day": 12}, ""),
    ],
    ids=[
        "year",
        "month",
        "no-year-leap",
        "invalid-day",
        "boolean",
        "huge-int",
        "day-without-month",
    ],
)
def test_employment_partial_dates_preserve_precision_without_inventing_components(
    value: object, expected: str
) -> None:
    from src.domains.agents.display.components.contact_facts import _partial_date

    assert _partial_date(value) == expected


def test_malformed_notifications_do_not_hide_valid_siblings_or_escape_html() -> None:
    markup = CalendarCard().render(
        {
            "summary": "Garden",
            "notificationSettings": {
                "notifications": [
                    None,
                    {"type": {}},
                    {"type": "agenda", "method": "email"},
                    {"type": "<script>inert</script>", "method": "email"},
                ]
            },
        },
        RenderContext(language="en"),
    )
    assert "Daily agenda" in markup
    assert "<script>inert</script>" not in markup


def test_no_employment_state_or_calendar_preferences_are_invented_from_absence() -> None:
    context = RenderContext(language="en")
    assert "Current organization" not in ContactCard().render(
        {"names": [{"displayName": "Garden keeper"}], "organizations": [{"name": "Garden"}]},
        context,
    )
    markup = CalendarCard().render({"summary": "Garden"}, context)
    assert (
        "Automatic invitation acceptance" not in markup
        and "Removed from calendar list" not in markup
    )


def test_calendar_received_location_owner_notifications_and_restricted_writer_role() -> None:
    output = ListCalendarsTool().format_registry_response(
        {
            "calendars": [
                {
                    "id": "calendar",
                    "summary": "Garden",
                    "accessRole": "writerWithoutPrivateAccess",
                    "location": "22 Garden Street",
                    "dataOwner": "garden@example.test",
                    "deleted": False,
                    "autoAcceptInvitations": True,
                    "notificationSettings": {
                        "notifications": [
                            {"type": "eventCreation", "method": "email"},
                            {"type": "agenda", "method": "email"},
                        ]
                    },
                }
            ],
            "total": 1,
        }
    )
    markup = CalendarCard().render(
        card_payload(next(iter(output.registry_updates.values()))), RenderContext(language="en")
    )
    for fact in (
        "22 Garden Street",
        "garden@example.test",
        "private details hidden",
        "New events",
        "Daily agenda",
        "Automatic invitation acceptance",
        "Yes",
        "No",
    ):
        assert fact in markup
    assert "manager access" not in markup


def test_contact_received_primary_phonetics_and_organization_periods() -> None:
    output = NativeReferenceOutput().build_contacts_output(
        [
            {
                "resourceName": "people/contact",
                "names": [
                    {"displayName": "Garden keeper", "phoneticFullName": "Received pronunciation"}
                ],
                "organizations": [
                    {
                        "name": "Garden company",
                        "title": "Keeper",
                        "type": "work",
                        "current": False,
                        "startDate": {"year": 2021, "month": 4, "day": 5},
                        "endDate": {"year": 2023, "month": 6, "day": 7},
                    }
                ],
            }
        ]
    )
    markup = ContactCard().render(
        card_payload(next(iter(output.registry_updates.values()))), RenderContext(language="en")
    )
    for fact in (
        "Received pronunciation",
        "2021-04-05",
        "2023-06-07",
        "Current organization",
        "No",
    ):
        assert fact in markup
