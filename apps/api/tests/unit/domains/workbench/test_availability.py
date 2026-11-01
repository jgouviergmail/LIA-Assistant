"""What the « Tools » rail shows: four states per tool, read in one short session (ADR-369).

``ready`` — the category's active provider (or the Drive / Hue row) is usable;
``reconnect_required`` — it broke and is one click from repair (ERROR, never a
deliberate REVOKED); ``unavailable`` — the instance withholds every provider of
the tool (the administrator's global switch); ``not_connected`` — otherwise,
drawn in « To connect » (D6). The features and bounds published are the active
provider's, so the page offers exactly what the provider accepts (ADR-184).
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.connectors.models import ConnectorStatus, ConnectorType
from src.domains.workbench import availability
from src.domains.workbench.availability import read_availability
from src.domains.workbench.features import WorkbenchFeature, WorkbenchTool

pytestmark = pytest.mark.unit

USER = uuid.uuid4()


class _Units:
    opened = 0

    def __init__(self, service: Any) -> None:
        self.service = service

    @contextlib.asynccontextmanager
    async def unit_of_work(self) -> AsyncIterator[Any]:
        _Units.opened += 1
        yield self.service


def _service(rows: dict[ConnectorType, ConnectorStatus], disabled: set[ConnectorType]) -> Any:
    service = MagicMock()
    service.get_user_connectors = AsyncMock(
        return_value=SimpleNamespace(
            connectors=[
                SimpleNamespace(connector_type=kind, status=status) for kind, status in rows.items()
            ]
        )
    )
    service.repository.get_all_global_configs = AsyncMock(
        return_value=[SimpleNamespace(connector_type=kind, is_enabled=False) for kind in disabled]
    )
    return service


async def _read(
    rows: dict[ConnectorType, ConnectorStatus],
    *,
    active: dict[str, ConnectorType | None],
    disabled: set[ConnectorType] | None = None,
) -> dict[WorkbenchTool, Any]:
    service = _service(rows, disabled or set())

    async def resolve(user_id: Any, category: str, _service: Any) -> ConnectorType | None:
        return active.get(category)

    _Units.opened = 0
    with (
        patch.object(availability, "DetachedConnectorService", return_value=_Units(service)),
        patch.object(availability, "resolve_active_connector", side_effect=resolve),
    ):
        answer = await read_availability(USER)
    assert _Units.opened == 1, "the whole rail is read in ONE short session"
    return {item.tool: item for item in answer.tools}


async def test_an_active_provider_is_ready_with_its_own_gestures() -> None:
    tools = await _read(
        {ConnectorType.GOOGLE_GMAIL: ConnectorStatus.ACTIVE},
        active={"email": ConnectorType.GOOGLE_GMAIL},
    )
    mail = tools[WorkbenchTool.MAIL]
    assert (mail.state, mail.provider) == ("ready", "google_gmail")
    assert WorkbenchFeature.LABELS in mail.features


async def test_outlook_contacts_publish_the_slots_their_client_enforces() -> None:
    """The editor is told what Exchange holds — the very constants the client refuses beyond."""
    from src.domains.connectors.clients.normalizers.contact_values import ContactValuesRefused
    from src.domains.connectors.clients.normalizers.microsoft_contacts_normalizer import (
        contact_value_fields,
    )

    tools = await _read(
        {ConnectorType.MICROSOFT_CONTACTS: ConnectorStatus.ACTIVE},
        active={"contacts": ConnectorType.MICROSOFT_CONTACTS},
    )
    bounds = tools[WorkbenchTool.CONTACTS].bounds
    emails = [{"value": f"{n}@x.org", "type": None} for n in range(bounds["emails_max"])]
    contact_value_fields({}, emails=emails)  # the published bound itself passes
    with pytest.raises(ContactValuesRefused):
        contact_value_fields({}, emails=[*emails, {"value": "one@more.org", "type": None}])


@pytest.mark.parametrize("provider", [ConnectorType.GOOGLE_TASKS, ConnectorType.MICROSOFT_TASKS])
async def test_task_providers_publish_the_text_bounds_the_routes_enforce(
    provider: ConnectorType,
) -> None:
    """The editor's maxLength is the very bound the request schema refuses beyond (ADR-184)."""
    from pydantic import ValidationError

    from src.domains.workbench.schemas.tasks import NewTask

    tools = await _read({provider: ConnectorStatus.ACTIVE}, active={"tasks": provider})
    bounds = tools[WorkbenchTool.TASKS].bounds
    key = {"list_id": "l1", "idempotency_key": uuid.uuid4()}
    NewTask(title="t" * bounds["title_max_chars"], notes="n" * bounds["notes_max_chars"], **key)
    with pytest.raises(ValidationError):
        NewTask(title="t" * (bounds["title_max_chars"] + 1), **key)
    with pytest.raises(ValidationError):
        NewTask(title="t", notes="n" * (bounds["notes_max_chars"] + 1), **key)


@pytest.mark.parametrize(
    "provider",
    [ConnectorType.GOOGLE_GMAIL, ConnectorType.MICROSOFT_OUTLOOK, ConnectorType.APPLE_EMAIL],
)
async def test_mail_providers_publish_the_search_bound_the_listing_enforces(
    provider: ConnectorType,
) -> None:
    """The search box's maxLength is the very bound the listing refuses beyond (ADR-184)."""
    from pydantic import ValidationError

    from src.domains.workbench.schemas.mail import MailListing

    tools = await _read({provider: ConnectorStatus.ACTIVE}, active={"email": provider})
    bound = tools[WorkbenchTool.MAIL].bounds["search_max_chars"]
    MailListing(q="w" * bound)
    with pytest.raises(ValidationError):
        MailListing(q="w" * (bound + 1))


async def test_mail_providers_publish_the_bounds_a_message_is_refused_beyond() -> None:
    """The composer's limits are the very bounds the send refuses beyond (ADR-184)."""
    from pydantic import ValidationError

    from src.domains.workbench.schemas.mail_compose import NewMessage

    tools = await _read(
        {ConnectorType.GOOGLE_GMAIL: ConnectorStatus.ACTIVE},
        active={"email": ConnectorType.GOOGLE_GMAIL},
    )
    bounds = tools[WorkbenchTool.MAIL].bounds
    key = {"idempotency_key": uuid.uuid4()}
    address = "a@example.org".rjust(bounds["recipient_max_chars"], "a")
    NewMessage(
        to=[address] * bounds["recipients_max"],
        subject="s" * bounds["subject_max_chars"],
        body="b" * bounds["body_max_chars"],
        **key,
    )
    for beyond in (
        {"to": ["a@example.org"] * (bounds["recipients_max"] + 1)},
        {"to": ["a" + address]},
        {"to": ["a@example.org"], "subject": "s" * (bounds["subject_max_chars"] + 1)},
        {"to": ["a@example.org"], "body": "b" * (bounds["body_max_chars"] + 1)},
    ):
        with pytest.raises(ValidationError):
            NewMessage(**beyond, **key)


@pytest.mark.parametrize(
    "provider",
    [ConnectorType.GOOGLE_GMAIL, ConnectorType.MICROSOFT_OUTLOOK, ConnectorType.APPLE_EMAIL],
)
async def test_mail_providers_publish_what_a_message_carries_in_files(
    provider: ConnectorType,
) -> None:
    """The published ceiling IS the client's own (ADR-321: derived, never re-typed)."""
    from pydantic import ValidationError

    from src.domains.connectors.clients.apple_email_client import AppleEmailClient
    from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
    from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
    from src.domains.workbench.schemas.mail_compose import NewMessage

    client_class = {
        ConnectorType.GOOGLE_GMAIL: GoogleGmailClient,
        ConnectorType.MICROSOFT_OUTLOOK: MicrosoftOutlookClient,
        ConnectorType.APPLE_EMAIL: AppleEmailClient,
    }[provider]
    tools = await _read({provider: ConnectorStatus.ACTIVE}, active={"email": provider})
    bounds = tools[WorkbenchTool.MAIL].bounds

    assert bounds["attachments_max_bytes"] == client_class.OUTGOING_FILE_MAX_BYTES
    files = [uuid.uuid4() for _ in range(bounds["attachments_max"] + 1)]
    NewMessage(to=["a@example.org"], attachment_ids=files[:-1], idempotency_key=uuid.uuid4())
    with pytest.raises(ValidationError):
        NewMessage(to=["a@example.org"], attachment_ids=files, idempotency_key=uuid.uuid4())


async def test_mail_providers_publish_the_shortest_recipient_query_searched() -> None:
    """Below it the matcher searches nothing: the composer asks nothing (ADR-184)."""
    from src.domains.email_share import recipients

    tools = await _read(
        {ConnectorType.APPLE_EMAIL: ConnectorStatus.ACTIVE},
        active={"email": ConnectorType.APPLE_EMAIL},
    )
    bound = tools[WorkbenchTool.MAIL].bounds["recipient_query_min_chars"]
    assert bound == recipients.EMAIL_SHARE_RECIPIENT_QUERY_MIN_CHARS


@pytest.mark.parametrize(
    "provider",
    [
        ConnectorType.GOOGLE_CALENDAR,
        ConnectorType.MICROSOFT_CALENDAR,
        ConnectorType.APPLE_CALENDAR,
    ],
)
async def test_calendar_providers_publish_the_shortest_guest_query_searched(
    provider: ConnectorType,
) -> None:
    """The guests are suggested by the same matcher as a message's recipients (owner,
    2026-10-31): the editor reads the shortest query it searches from its own tool."""
    from src.domains.email_share import recipients

    tools = await _read({provider: ConnectorStatus.ACTIVE}, active={"calendar": provider})
    bound = tools[WorkbenchTool.CALENDAR].bounds["recipient_query_min_chars"]
    assert bound == recipients.EMAIL_SHARE_RECIPIENT_QUERY_MIN_CHARS


async def test_outlook_is_never_offered_gmail_labels() -> None:
    tools = await _read(
        {ConnectorType.MICROSOFT_OUTLOOK: ConnectorStatus.ACTIVE},
        active={"email": ConnectorType.MICROSOFT_OUTLOOK},
    )
    assert WorkbenchFeature.LABELS not in tools[WorkbenchTool.MAIL].features


async def test_a_broken_provider_asks_for_a_reconnection() -> None:
    tools = await _read(
        {ConnectorType.MICROSOFT_CALENDAR: ConnectorStatus.ERROR},
        active={},
    )
    calendar = tools[WorkbenchTool.CALENDAR]
    assert (calendar.state, calendar.provider) == ("reconnect_required", "microsoft_calendar")


async def test_a_revoked_provider_is_simply_not_connected() -> None:
    """A deliberate disconnection is never nagged about (ADR-134 V2)."""
    tools = await _read({ConnectorType.GOOGLE_TASKS: ConnectorStatus.REVOKED}, active={})
    assert tools[WorkbenchTool.TASKS].state == "not_connected"
    assert tools[WorkbenchTool.TASKS].features == []


async def test_drive_and_hue_are_read_from_their_own_rows() -> None:
    tools = await _read(
        {
            ConnectorType.GOOGLE_DRIVE: ConnectorStatus.ACTIVE,
            ConnectorType.PHILIPS_HUE: ConnectorStatus.ERROR,
        },
        active={},
    )
    assert (tools[WorkbenchTool.FILES].state, tools[WorkbenchTool.FILES].provider) == (
        "ready",
        "google_drive",
    )
    assert tools[WorkbenchTool.LIGHTS].state == "reconnect_required"


async def test_a_tool_the_instance_withholds_entirely_is_unavailable() -> None:
    tools = await _read({}, active={}, disabled={ConnectorType.GOOGLE_DRIVE})
    assert tools[WorkbenchTool.FILES].state == "unavailable"


async def test_one_withheld_provider_of_three_leaves_the_tool_to_connect() -> None:
    tools = await _read({}, active={}, disabled={ConnectorType.GOOGLE_GMAIL})
    assert tools[WorkbenchTool.MAIL].state == "not_connected"


async def test_every_tool_is_answered_in_rail_order() -> None:
    tools = await _read({}, active={})
    assert list(tools) == [
        WorkbenchTool.MAIL,
        WorkbenchTool.CALENDAR,
        WorkbenchTool.TASKS,
        WorkbenchTool.CONTACTS,
        WorkbenchTool.FILES,
        WorkbenchTool.LIGHTS,
    ]


async def test_the_published_page_never_exceeds_the_provider_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(availability.settings, "workbench_page_size", 50)
    monkeypatch.setattr(availability.settings, "api_max_items_per_request", 25)
    service = _service({}, set())
    with (
        patch.object(availability, "DetachedConnectorService", return_value=_Units(service)),
        patch.object(availability, "resolve_active_connector", AsyncMock(return_value=None)),
    ):
        answer = await read_availability(USER)
    assert answer.limits.page_size == 25
