"""Provider wire shapes pass through their real normalizers and registry builders."""

from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace
from uuid import uuid4

import pytest
import vobject
from imap_tools import MailMessage

from src.domains.agents.display.card_navigation import stamp_card_targets
from src.domains.agents.tools.calendar_list_tools import ListCalendarsTool
from src.domains.agents.tools.hue_tools import ListHueLightsTool
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.connectors.clients.normalizers.calendar_normalizer import (
    normalize_calendar,
    normalize_vevent,
)
from src.domains.connectors.clients.normalizers.contacts_normalizer import normalize_vcard
from src.domains.connectors.clients.normalizers.email_normalizer import normalize_imap_message
from src.domains.connectors.clients.normalizers.imap_handles import (
    read_message_handle,
    scope_digest,
)
from src.domains.connectors.clients.normalizers.microsoft_calendar_normalizer import (
    normalize_graph_calendar,
    normalize_graph_event,
)
from src.domains.connectors.clients.normalizers.microsoft_contacts_normalizer import (
    normalize_graph_contact,
)
from src.domains.connectors.clients.normalizers.microsoft_email_normalizer import (
    normalize_graph_message,
)
from src.domains.connectors.clients.normalizers.microsoft_tasks_normalizer import (
    normalize_graph_task,
)
from src.domains.connectors.clients.normalizers.onedrive_normalizer import normalize_drive_item
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import (
    AppleCredentials,
    ConnectorCredentials,
    HueBridgeCredentials,
    HueConnectionMode,
)
from src.domains.workbench.card_targets import CARD_TARGET_FIELD, read_card_target

pytestmark = pytest.mark.unit
_BUILDER = ToolOutputMixin()


def _imap() -> dict[str, object]:
    message = MailMessage(
        [(b"1 (UID 41 BODY[] {80}", b"From: sender@example.test\r\nSubject: Source\r\n\r\nBody")]
    )
    return normalize_imap_message(
        message, "Archives", scope=scope_digest("owner@example.test", "Archives", 22)
    )


def _caldav_event() -> dict[str, object]:
    calendar = vobject.readOne(
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:real-uid\r\nSUMMARY:Appointment\r\nDTSTART:20261108T100000Z\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    )
    return normalize_vevent(
        SimpleNamespace(vobject_instance=calendar, url="https://cal.test/e.ics")
    )


@dataclass(frozen=True)
class _Case:
    provider: ConnectorType
    produce: Callable[[], UnifiedToolOutput]
    item_id: str
    container: str | None = None


_CASES = [
    _Case(
        ConnectorType.GOOGLE_GMAIL,
        lambda: _BUILDER.build_emails_output([{"id": "gmail-id", "subject": "Source"}]),
        "gmail-id",
    ),
    _Case(
        ConnectorType.MICROSOFT_OUTLOOK,
        lambda: _BUILDER.build_emails_output(
            [
                normalize_graph_message(
                    {"id": "AAMk+email=", "subject": "Source", "parentFolderId": "not-normalized"}
                )
            ]
        ),
        "AAMk+email=",
    ),
    _Case(
        ConnectorType.APPLE_EMAIL,
        lambda: _BUILDER.build_emails_output([_imap()]),
        str(_imap()["id"]),
    ),
    _Case(
        ConnectorType.GOOGLE_CONTACTS,
        lambda: _BUILDER.build_contacts_output(
            [{"resourceName": "people/p1", "names": [{"displayName": "Person"}]}]
        ),
        "people/p1",
    ),
    _Case(
        ConnectorType.MICROSOFT_CONTACTS,
        lambda: _BUILDER.build_contacts_output(
            [normalize_graph_contact({"id": "graph-person", "displayName": "Person"})]
        ),
        "people/graph-person",
    ),
    _Case(
        ConnectorType.APPLE_CONTACTS,
        lambda: _BUILDER.build_contacts_output(
            [
                normalize_vcard(
                    "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Person\r\nUID:person\r\nEND:VCARD\r\n",
                    resource_name="people/apple-person",
                )
            ]
        ),
        "people/apple-person",
    ),
    _Case(
        ConnectorType.GOOGLE_CALENDAR,
        lambda: _BUILDER.build_events_output(
            [{"id": "google-event", "start": {"date": "2026-11-08"}}], calendar_id="google-calendar"
        ),
        "google-event",
        "google-calendar",
    ),
    _Case(
        ConnectorType.MICROSOFT_CALENDAR,
        lambda: _BUILDER.build_events_output(
            [
                normalize_graph_event(
                    {
                        "id": "graph-event",
                        "start": {"dateTime": "2026-11-08T10:00:00", "timeZone": "UTC"},
                    }
                )
            ],
            calendar_id="graph-calendar",
        ),
        "graph-event",
        "graph-calendar",
    ),
    _Case(
        ConnectorType.APPLE_CALENDAR,
        lambda: _BUILDER.build_events_output(
            [_caldav_event()], calendar_id="https://cal.test/calendar/"
        ),
        "real-uid",
        "https://cal.test/calendar/",
    ),
    _Case(
        ConnectorType.GOOGLE_TASKS,
        lambda: _BUILDER.build_tasks_output(
            [{"id": "google-task", "title": "Task"}], task_list_id="google-list"
        ),
        "google-task",
        "google-list",
    ),
    _Case(
        ConnectorType.MICROSOFT_TASKS,
        lambda: _BUILDER.build_tasks_output(
            [normalize_graph_task({"id": "graph-task", "title": "Task"})], task_list_id="graph-list"
        ),
        "graph-task",
        "graph-list",
    ),
    _Case(
        ConnectorType.GOOGLE_DRIVE,
        lambda: _BUILDER.build_files_output([{"id": "drive-file", "name": "File"}]),
        "drive-file",
    ),
    _Case(
        ConnectorType.MICROSOFT_ONEDRIVE,
        lambda: _BUILDER.build_files_output(
            [normalize_drive_item({"id": "onedrive-folder", "name": "Folder", "folder": {}})]
        ),
        "onedrive-folder",
    ),
    _Case(
        ConnectorType.PHILIPS_HUE,
        lambda: ListHueLightsTool(
            tool_name="list_hue_lights", operation="list"
        ).format_registry_response(
            {
                "data": {
                    "lights": [
                        {
                            "id": "lamp-uuid",
                            "metadata": {"name": "Desk"},
                            "owner": {"rid": "device-id"},
                        }
                    ]
                }
            }
        ),
        "lamp-uuid",
    ),
]


@pytest.mark.parametrize("case", _CASES, ids=[case.provider.value for case in _CASES])
def test_native_provider_payload_reaches_the_same_address_after_roundtrip(case: _Case) -> None:
    user = uuid4()
    credentials: AppleCredentials | HueBridgeCredentials | ConnectorCredentials
    if case.provider.is_apple:
        credentials = AppleCredentials(apple_id="owner@example.test", app_password="unused")
    elif case.provider.is_hue:
        credentials = HueBridgeCredentials(
            connection_mode=HueConnectionMode.LOCAL, bridge_id="bridge-id", api_key="unused"
        )
    else:
        credentials = ConnectorCredentials(access_token="unused", account_binding="grant")
    output = case.produce()
    stamp_card_targets(
        output,
        client=SimpleNamespace(credentials=credentials),
        provider=case.provider,
        user_id=user,
        timezone="UTC",
    )
    restored = UnifiedToolOutput.model_validate_json(output.model_dump_json())
    item = next(iter(restored.registry_updates.values()))
    proof = read_card_target(item.meta.display[CARD_TARGET_FIELD], user)
    assert proof is not None and proof.provider == case.provider
    assert (proof.target.item_id, proof.target.container_id) == (case.item_id, case.container)
    if case.provider == ConnectorType.APPLE_EMAIL:
        handle = read_message_handle(proof.target.item_id)
        assert handle is not None and handle.scope_digest and handle.folder_digest
    if case.provider == ConnectorType.MICROSOFT_ONEDRIVE:
        assert proof.target.is_folder


@pytest.mark.parametrize(
    "provider,calendar",
    [
        (ConnectorType.GOOGLE_CALENDAR, {"id": "google-calendar", "summary": "Work"}),
        (
            ConnectorType.MICROSOFT_CALENDAR,
            normalize_graph_calendar({"id": "graph-calendar", "name": "Work"}),
        ),
        (
            ConnectorType.APPLE_CALENDAR,
            normalize_calendar(SimpleNamespace(url="https://cal.test/calendar/"), "Work"),
        ),
    ],
)
def test_calendar_list_producers_keep_the_real_calendar_id(
    provider: ConnectorType, calendar: dict[str, object]
) -> None:
    output = ListCalendarsTool().format_registry_response({"calendars": [calendar], "total": 1})
    user = uuid4()
    stamp_card_targets(
        output,
        client=SimpleNamespace(
            credentials=ConnectorCredentials(access_token="unused", account_binding="grant")
        ),
        provider=provider,
        user_id=user,
        timezone="UTC",
    )
    item = next(
        iter(
            UnifiedToolOutput.model_validate_json(
                output.model_dump_json()
            ).registry_updates.values()
        )
    )
    proof = read_card_target(item.meta.display[CARD_TARGET_FIELD], user)
    assert proof is not None and proof.target.item_id == calendar["id"]
