"""Native card addresses survive persistence without entering the model's facts."""

from dataclasses import dataclass
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage

from src.domains.agents.data_registry.card_payload import card_payload
from src.domains.agents.data_registry.models import RegistryItem, RegistryItemMeta, RegistryItemType
from src.domains.agents.display.card_collection import render_collection_item
from src.domains.agents.display.card_navigation import stamp_card_targets
from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.event_card import EventCard
from src.domains.agents.display.llm_serializer import payload_to_text
from src.domains.agents.display.model_history import with_model_view
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.react_tool_wrapper import extract_data_for_llm
from src.domains.agents.utils.message_filters import filter_for_llm_context
from src.domains.connectors.models import ConnectorType
from src.domains.workbench.card_targets import CARD_KIND_FIELD, CARD_TARGET_FIELD, read_card_target

pytestmark = pytest.mark.unit


@dataclass
class _Credentials:
    account_binding: str = "grant-a"


@dataclass
class _Client:
    credentials: _Credentials


@pytest.mark.parametrize(
    "kind,provider,payload,item_id,container",
    [
        (RegistryItemType.EMAIL, ConnectorType.GOOGLE_GMAIL, {"id": "mail/+="}, "mail/+=", None),
        (
            RegistryItemType.EMAIL,
            ConnectorType.APPLE_EMAIL,
            {"id": "41.abcd.1234", "mail_folder": "Archives été"},
            "41.abcd.1234",
            "Archives été",
        ),
        (
            RegistryItemType.EVENT,
            ConnectorType.GOOGLE_CALENDAR,
            {"id": "e", "calendar_id": "actual-calendar"},
            "e",
            "actual-calendar",
        ),
        (
            RegistryItemType.CALENDAR,
            ConnectorType.MICROSOFT_CALENDAR,
            {"id": "calendar/+="},
            "calendar/+=",
            None,
        ),
        (
            RegistryItemType.CONTACT,
            ConnectorType.GOOGLE_CONTACTS,
            {"resourceName": "people/p1"},
            "people/p1",
            None,
        ),
        (
            RegistryItemType.TASK,
            ConnectorType.MICROSOFT_TASKS,
            {"id": "t", "tasklist_id": "list-a"},
            "t",
            "list-a",
        ),
        (
            RegistryItemType.FILE,
            ConnectorType.MICROSOFT_ONEDRIVE,
            {"id": "drive:file", "mimeType": "application/vnd.google-apps.folder"},
            "drive:file",
            None,
        ),
        (
            RegistryItemType.HUE_LIGHT,
            ConnectorType.PHILIPS_HUE,
            {"light_id": "lamp", "room": "owner-device-not-room"},
            "lamp",
            None,
        ),
    ],
)
def test_only_actual_provider_ids_and_received_scopes_are_projected(
    kind: RegistryItemType,
    provider: ConnectorType,
    payload: dict[str, object],
    item_id: str,
    container: str | None,
) -> None:
    item = RegistryItem(
        id="registry-id-is-not-provider-id",
        type=kind,
        payload=payload,
        meta=RegistryItemMeta(source="not-authority"),
    )
    output = UnifiedToolOutput.data_success(message="records", registry_updates={item.id: item})
    user = uuid4()
    stamp_card_targets(
        output, client=_Client(_Credentials()), provider=provider, user_id=user, timezone="UTC"
    )
    restored = UnifiedToolOutput.model_validate_json(output.model_dump_json())
    stored = restored.registry_updates[item.id]
    token = stored.meta.display[CARD_TARGET_FIELD]
    proof = read_card_target(token, user)
    assert proof is not None and proof.provider == provider
    assert proof.target.item_id == item_id and proof.target.container_id == container
    assert proof.target.is_folder is (kind == RegistryItemType.FILE)
    assert stored.payload == payload
    assert token not in extract_data_for_llm(restored)
    assert token not in payload_to_text(stored.payload)


@pytest.mark.parametrize(
    "kind,payload",
    [
        (RegistryItemType.EVENT, {"id": "e"}),
        (RegistryItemType.TASK, {"id": "t"}),
        (RegistryItemType.EMAIL, {"url": "https://mail.google.com/#inbox/not-an-id"}),
        (RegistryItemType.CONTACT, {"resourceName": {"id": "malformed"}}),
    ],
)
def test_missing_identity_is_never_reconstructed_from_url_or_registry_id(
    kind: RegistryItemType, payload: dict[str, object]
) -> None:
    item = RegistryItem(
        id="email_guess",
        type=kind,
        payload=payload,
        meta=RegistryItemMeta(source="gmail", display={CARD_TARGET_FIELD: "untrusted"}),
    )
    output = UnifiedToolOutput.data_success(message="records", registry_updates={item.id: item})
    stamp_card_targets(
        output,
        client=_Client(_Credentials()),
        provider=ConnectorType.GOOGLE_GMAIL,
        user_id=uuid4(),
        timezone="UTC",
    )
    assert CARD_TARGET_FIELD not in item.meta.display
    assert item.meta.display[CARD_KIND_FIELD] == kind.value.lower()
    assert item.payload == payload


def test_actual_event_builder_reaches_html_after_serialization() -> None:
    output = ToolOutputMixin().build_events_output(
        [{"id": "evt", "summary": "Late meeting", "start": {"dateTime": "2026-11-08T23:30:00Z"}}],
        calendar_id="calendar-a",
        user_timezone="Asia/Tokyo",
        locale="en",
    )
    user = uuid4()
    stamp_card_targets(
        output,
        client=_Client(_Credentials()),
        provider=ConnectorType.GOOGLE_CALENDAR,
        user_id=user,
        timezone="Asia/Tokyo",
    )
    restored = UnifiedToolOutput.model_validate_json(output.model_dump_json())
    item = next(iter(restored.registry_updates.values()))
    payload = card_payload(item)
    assert payload is not None
    data = {**payload, "_lia_card_ref": item.id}
    token = data[CARD_TARGET_FIELD]
    proof = read_card_target(token, user)
    assert proof is not None and proof.target.day == "2026-11-09"
    html = render_collection_item(EventCard(), data, RenderContext(language="en"))
    assert f'data-card-target="{token}"' in html and 'data-card-kind="event"' in html
    assert "Late meeting" in html
    without_action_reference = render_collection_item(
        EventCard(), payload, RenderContext(language="en")
    )
    assert f'data-card-target="{token}"' in without_action_reference
    assert "data-card-ref" not in without_action_reference
    answer = with_model_view(AIMessage(content=html), "One event.", restored.registry_updates)
    archived = AIMessage.model_validate_json(answer.model_dump_json())
    history = filter_for_llm_context([archived])
    assert history and "Late meeting" in str(history[0].content)
    assert token not in str(history[0].content)


def test_source_actions_are_marked_but_maps_and_meet_are_not() -> None:
    actions = EventCard()._build_default_actions(
        {
            "htmlLink": "https://calendar.test/evt",
            "location": "Museum",
            "conferenceData": {
                "entryPoints": [{"entryPointType": "video", "uri": "https://meet.test/call"}]
            },
        },
        RenderContext(language="en"),
    )
    assert [a["url"] for a in actions if a.get("card_open") == "true"] == [
        "https://calendar.test/evt"
    ]


@pytest.mark.parametrize("binding,success", [("", True), ("grant-a", False)])
def test_absent_source_or_declared_failure_cannot_preserve_a_supplied_target(
    binding: str,
    success: bool,
) -> None:
    item = RegistryItem(
        id="email-1",
        type=RegistryItemType.EMAIL,
        payload={"id": "received-id"},
        meta=RegistryItemMeta(
            source="gmail", display={CARD_TARGET_FIELD: "untrusted", "body": "kept"}
        ),
    )
    output = UnifiedToolOutput(
        message="result",
        success=success,
        registry_updates={item.id: item},
        error_code=None if success else "provider_error",
    )
    stamp_card_targets(
        output,
        client=_Client(_Credentials(binding)),
        provider=ConnectorType.GOOGLE_GMAIL,
        user_id=uuid4(),
        timezone="UTC",
    )
    assert item.meta.display == {CARD_KIND_FIELD: "email", "body": "kept"}
