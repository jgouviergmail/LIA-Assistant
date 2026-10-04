"""Native supplemental facts after JSON registry round-trip, without provider calls."""

from src.domains.agents.data_registry.card_payload import card_payload
from src.domains.agents.data_registry.models import RegistryItem
from src.domains.agents.tools.calendar_tools import ListCalendarsTool
from src.domains.agents.tools.hue_tools import ListHueLightsTool
from src.domains.agents.workboard.context import ticket_registry_items
from tests.helpers.card_microsoft_reference import NativeReferenceOutput


def native_detail_domains(language: str) -> dict[str, dict[str, object]]:
    lights = ListHueLightsTool(
        tool_name="list_hue_lights", operation="list"
    ).format_registry_response(
        {
            "data": {
                "lights": [
                    {
                        "id": "reference-light",
                        "metadata": {"name": "Lampe du bureau"},
                        "on": {"on": True},
                        "dimming": {"brightness": 0},
                        "color": {"xy": {"x": 0.3, "y": 0.4}},
                        "color_temperature": {
                            "mirek": 250,
                            "mirek_valid": True,
                            "mirek_schema": {"mirek_minimum": 153, "mirek_maximum": 500},
                        },
                    }
                ]
            }
        }
    )
    calendars = ListCalendarsTool().format_registry_response(
        {
            "calendars": [
                {
                    "id": "reference-calendar",
                    "summary": "Original garden",
                    "summaryOverride": "My garden",
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
    contacts = NativeReferenceOutput().build_contacts_output(
        [
            {
                "resourceName": "people/reference-garden-keeper",
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
    events = NativeReferenceOutput().build_events_output(
        [
            {
                "id": "reference-conference",
                "summary": "Meet the gardeners",
                "start": {"dateTime": "2026-10-05T09:00:00+02:00"},
                "end": {"dateTime": "2026-10-05T10:00:00+02:00"},
                "reminders": {"useDefault": False},
                "conferenceData": {
                    "conferenceSolution": {"name": "Garden meeting"},
                    "conferenceId": "PROVIDER_ID_NOT_DISPLAYED",
                    "entryPoints": [
                        {
                            "entryPointType": "video",
                            "uri": "https://meet.example.test/first",
                            "label": "Garden video",
                        },
                        {
                            "entryPointType": "video",
                            "uri": "https://meet.example.test/second",
                            "label": "Alternate video",
                        },
                        {
                            "entryPointType": "phone",
                            "uri": "tel:+33123456789",
                            "label": "+33 1 23 45 67 89",
                            "pin": "123456",
                        },
                    ],
                },
            }
        ],
        locale=language,
        user_timezone="Europe/Paris",
    )
    tickets = ticket_registry_items(
        [
            {
                "id": "reference-ticket",
                "title": "Préparer la visite",
                "status": "in_progress",
                "priority": "medium",
                "assignee_kind": "lia",
            }
        ],
        tool_name="get_ticket_tool",
        display_by_id={
            "reference-ticket": {
                "description": "Received sentence. " * 40 + "LAST_DESCRIPTION",
                "children": [{"title": "Step one", "status": "done", "priority": "urgent"}],
                "comments": [{"author": "lia", "body": "Received comment. LAST_COMMENT"}],
                "last_run": {
                    "outcome": "skipped_quota",
                    "cost_eur": 0,
                    "tokens_in": 0,
                    "tokens_out": 12,
                },
            }
        },
    )
    return {
        domain: {
            domain: [
                card_payload(RegistryItem.model_validate_json(item.model_dump_json()))
                for item in items.values()
            ]
        }
        for domain, items in (
            ("hues", lights.registry_updates),
            ("contacts", contacts.registry_updates),
            ("calendars", calendars.registry_updates),
            ("events", events.registry_updates),
            ("tickets", tickets),
        )
    }
