"""Native semantic paths must resolve against the payloads the tools really build.

These probes exercise the provider and internal projections, not hand-written
tool output. They keep resource handles, display names, partial dates and
measurements distinct at the boundary where the planner obtains values.
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from src.domains.agents.orchestration.condition_evaluator import ReferenceResolver
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.registry.semantic_inventory import collect_static_manifests
from src.domains.agents.services.devops_ssh_service import DevOpsTaskResult
from src.domains.agents.tools import devops_tools, diagnostics_tools
from src.domains.agents.tools.email_self_tools import _sent
from src.domains.agents.tools.generated_files_tools import _file_item
from src.domains.agents.tools.hue_tools import ListHueLightsTool
from src.domains.agents.tools.journal_search_tools import _entry_item
from src.domains.agents.tools.memory_search_tools import _memory_item
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.places_formatting import _format_place
from src.domains.agents.tools.places_tools import GetCurrentLocationTool
from src.domains.agents.tools.relation_read_tools import (
    _calls_block,
    _open_loops_block,
    _peer_messages_block,
)
from src.domains.agents.tools.workboard_tools import _ticket_summary
from src.domains.attachments.models import Attachment, AttachmentOrigin
from src.domains.connectors.clients.normalizers.email_message import EmailAttachment, EmailMessage
from src.domains.diagnostics.models import Incident
from src.domains.health_metrics.service import HealthMetricsService
from src.domains.journals.models import JournalEntry, JournalEntryLevel
from src.domains.memories.models import Memory
from src.domains.relations.schemas import (
    IdentityConfidence,
    RelationCall,
    RelationDetail,
    RelationOpenLoop,
    RelationPeerMessage,
)
from src.domains.workboard.models import WorkboardTicket
from tests.helpers.runtime_context import make_tool_runtime
from tests.unit.domains.agents.registry.reference_harness import (
    DECLARED_TYPE_TO_PYTHON,
    completed_step,
)

pytestmark = pytest.mark.unit

_ID = UUID("11111111-2222-3333-4444-555555555555")
_WHEN = datetime(2026, 10, 6, 10, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def manifests() -> dict[str, ToolManifest]:
    return {manifest.name: manifest for manifest in collect_static_manifests()}


def _value(manifest: ToolManifest, data: dict[str, Any], path: str, semantic_type: str) -> Any:
    field = next(output for output in manifest.outputs if output.path == path)
    assert field.semantic_type == semantic_type
    value = ReferenceResolver().resolve(
        f"$steps.source.{path.replace('[]', '[0]')}", {"source": data}, None
    )
    assert (
        value is None and field.nullable or isinstance(value, DECLARED_TYPE_TO_PYTHON[field.type])
    )
    return value


def test_contact_notes_and_organization_are_chainable_scalars(
    manifests: dict[str, ToolManifest],
) -> None:
    output = ToolOutputMixin().build_contacts_output(
        contacts=[
            {
                "resourceName": "people/123",
                "names": [{"displayName": "Ada"}],
                "organizations": [{"name": "Acme"}],
                "biographies": [{"value": "Engineer"}],
                "birthdays": [{"date": {"month": 10, "day": 6}}],
            }
        ]
    )
    data = completed_step(output)
    manifest = manifests["get_contacts_tool"]
    assert _value(manifest, data, "contacts[].organizations[].name", "organization_name") == "Acme"
    assert _value(manifest, data, "contacts[].biographies[].value", "biography") == "Engineer"
    for container in ("contacts[].biographies", "contacts[].birthdays"):
        assert (
            next(field for field in manifest.outputs if field.path == container).semantic_type
            is None
        )
    # Yearless birthdays are partial records, never ISO dates or biography text.
    assert data["contacts"][0]["birthdays"][0]["date"] == {"month": 10, "day": 6}


@pytest.mark.parametrize("gmail_spelling", [False, True])
def test_email_attachments_preserve_provider_handle_and_filename(
    manifests: dict[str, ToolManifest], gmail_spelling: bool
) -> None:
    attachment = EmailAttachment(
        filename="contract.pdf", mimeType="application/pdf", size=100, attachmentId="part-1"
    ).model_dump()
    if gmail_spelling:
        attachment["attachment_id"] = attachment.pop("attachmentId")
        attachment["mime_type"] = attachment.pop("mimeType")
    message = EmailMessage(
        id="mail-1",
        threadId="thread-1",
        labelIds=["Label_1"],
        subject="Contract",
        from_="Ada <ada@example.com>",
        provider="google",
    ).model_dump(by_alias=True)
    message["attachments"] = [attachment]
    data = completed_step(ToolOutputMixin().build_emails_output([message]))
    manifest = manifests["get_emails_tool"]
    handle_key = "attachment_id" if gmail_spelling else "attachmentId"
    assert (
        _value(manifest, data, f"emails[].attachments[].{handle_key}", "email_attachment_id")
        == "part-1"
    )
    assert _value(manifest, data, "emails[].attachments[].filename", "file_name") == "contract.pdf"
    assert _value(manifest, data, "emails[].labelIds", "email_label_id") == ["Label_1"]
    consumer = manifests["get_email_attachment_tool"]
    params = {parameter.name: parameter.semantic_type for parameter in consumer.parameters}
    assert params["message_id"] == "message_id"
    assert params["attachment_id"] == "email_attachment_id"
    assert params["filename"] == "file_name"
    labels = manifests["list_labels_tool"]
    assert (
        next(field for field in labels.outputs if field.path == "labels[].name").semantic_type
        == "email_label"
    )


def test_all_day_calendar_start_is_normalized_before_semantic_chaining(
    manifests: dict[str, ToolManifest],
) -> None:
    output = ToolOutputMixin().build_events_output(
        events=[{"id": "event-1", "start": {"date": "2026-10-06"}, "end": {"date": "2026-10-07"}}],
        user_timezone="Europe/Paris",
    )
    value = _value(
        manifests["get_events_tool"],
        completed_step(output),
        "events[].start.dateTime",
        "event_start_datetime",
    )
    assert datetime.fromisoformat(value).utcoffset() is not None


def test_drive_owner_record_exposes_the_real_address_not_a_name_string(
    manifests: dict[str, ToolManifest],
) -> None:
    output = ToolOutputMixin().build_files_output(
        files=[
            {"id": "drive-1", "name": "report.pdf", "owners": [{"emailAddress": "ada@example.com"}]}
        ]
    )
    manifest = manifests["get_files_tool"]
    assert (
        next(field for field in manifest.outputs if field.path == "files[].owners").type == "array"
    )
    assert (
        _value(manifest, completed_step(output), "files[].owners[].emailAddress", "email_address")
        == "ada@example.com"
    )


def test_place_codes_and_coordinate_components_are_not_display_labels(
    manifests: dict[str, ToolManifest],
) -> None:
    place = _format_place(
        {
            "id": "place-1",
            "displayName": {"text": "Cafe"},
            "location": {"latitude": 48.85, "longitude": 2.35},
            "types": ["cafe"],
            "primaryTypeDisplayName": {"text": "Café"},
            "priceLevel": "PRICE_LEVEL_INEXPENSIVE",
        },
        language="fr",
    )
    data = completed_step(ToolOutputMixin().build_places_output([place]))
    manifest = manifests["get_places_tool"]
    assert _value(manifest, data, "places[].types[]", "place_type") == "cafe"
    assert _value(manifest, data, "places[].location.lat", "latitude") == 48.85
    assert _value(manifest, data, "places[].location.lon", "longitude") == 2.35
    assert _value(manifest, data, "places[].primary_type", "Text") == "Café"
    assert (
        next(param for param in manifest.parameters if param.name == "price_levels").semantic_type
        is None
    )
    # The current-location card carries a COUNTRY NAME, while its source is
    # metadata outside the payload — neither can be published as a country code.
    output = GetCurrentLocationTool().format_registry_response(
        {
            "success": True,
            "data": {
                "country": "France",
                "source": "browser",
                "location": {"lat": 48.85, "lon": 2.35},
            },
        }
    )
    location = manifests["get_current_location_tool"]
    assert _value(location, completed_step(output), "locations[].latitude", "latitude") == 48.85
    assert (
        next(
            field for field in location.outputs if field.path == "locations[].country"
        ).semantic_type
        is None
    )
    assert "locations[].source" not in {field.path for field in location.outputs}


def test_internal_dates_and_generated_filename_have_distinct_meanings(
    manifests: dict[str, ToolManifest],
) -> None:
    attachment = Attachment(
        id=_ID,
        original_filename="report.pdf",
        title="Report",
        file_size=123,
        origin=AttachmentOrigin.GENERATED_DOCUMENT.value,
        created_at=_WHEN,
        expires_at=None,
        shared_by_name=None,
    )
    generated = {"files": [_file_item(attachment, ZoneInfo("Europe/Paris"))]}
    manifest = manifests["find_generated_files_tool"]
    assert _value(manifest, generated, "files[].file_name", "file_name") == "report.pdf"
    assert _value(manifest, generated, "files[].expires", "datetime") is None
    assert "id" not in generated["files"][0]  # The listing exposes no attachment UUID.
    memory = Memory(content="Prefers short answers", category="preference", created_at=_WHEN)
    memories = {"memories": [_memory_item(memory, 0.8)]}
    assert (
        _value(manifests["search_memories_tool"], memories, "memories[].recorded_on", "Date")
        == "2026-10-06"
    )
    entry = JournalEntry(
        title="Preference",
        content="Keep it short",
        level=JournalEntryLevel.L1.value,
        created_at=_WHEN,
    )
    journal = {"entries": [_entry_item(entry, 0.8, ZoneInfo("Europe/Paris"))]}
    assert (
        _value(manifests["search_journal_tool"], journal, "entries[].kind", "journal_entry_kind")
        == "directive"
    )
    assert (
        _value(manifests["search_journal_tool"], journal, "entries[].written_on", "Date")
        == "2026-10-06"
    )


def test_workboard_summary_exposes_real_uuid_status_and_deadline(
    manifests: dict[str, ToolManifest],
) -> None:
    ticket = WorkboardTicket(
        id=_ID,
        title="Read the contract",
        status="todo",
        priority="high",
        start_at=None,
        due_at=_WHEN,
    )
    data = {"tickets": [_ticket_summary(ticket)]}
    manifest = manifests["list_tickets_tool"]
    assert _value(manifest, data, "tickets[].id", "ticket_id") == str(_ID)
    assert _value(manifest, data, "tickets[].status", "ticket_status") == "todo"
    assert datetime.fromisoformat(_value(manifest, data, "tickets[].due_at", "datetime")) == _WHEN
    # The write/read resolver accepts an exact title too: it is not a UUID-only input.
    parameter = manifests["update_ticket_tool"].parameters[0]
    assert parameter.name == "ticket" and parameter.semantic_type is None


def test_relation_projections_keep_content_and_deadlines_chainable(
    manifests: dict[str, ToolManifest],
) -> None:
    detail = RelationDetail(
        display_name="Ada",
        identity_confidence=IdentityConfidence.EXACT,
        memories=[],
        open_loops=[
            RelationOpenLoop(
                id="loop-1",
                subject="Review",
                direction="user_owes",
                due_hint=_WHEN,
                days_open=2,
                opened_at=_WHEN,
            )
        ],
        recent_calls=[
            RelationCall(id="call-1", objective="Review", summary="Agreed", created_at=_WHEN)
        ],
        peer_messages=[
            RelationPeerMessage(
                id="peer-1", direction="received", content="Ready", occurred_at=_WHEN
            )
        ],
    )
    for tool, builder, path, semantic in (
        ("get_calls_tool", _calls_block, "calls[].occurred_at", "datetime"),
        ("get_open_loops_tool", _open_loops_block, "open_loops[].due_hint", "datetime"),
        ("get_peer_messages_tool", _peer_messages_block, "peer_messages[].content", "Text"),
    ):
        key, page, _total = builder(detail, 1)
        assert _value(manifests[tool], {key: page}, path, semantic)


@pytest.mark.asyncio
async def test_health_overview_advertises_its_actual_nested_windows(
    manifests: dict[str, ToolManifest],
) -> None:
    service = HealthMetricsService(MagicMock())
    service.sample_repo.fetch_samples_kind = AsyncMock(return_value=[])
    overview = await service.compute_overview(_ID, time_min=_WHEN, time_max=_WHEN)
    output = UnifiedToolOutput.data_success(
        message="Overview", structured_data={"overview": overview}
    )
    data = completed_step(output)
    manifest = manifests["get_health_overview_tool"]
    assert "from_ts" not in {field.path for field in manifest.outputs}
    for kind in overview:
        assert (
            datetime.fromisoformat(_value(manifest, data, f"overview.{kind}.from_ts", "datetime"))
            == _WHEN
        )
        assert (
            datetime.fromisoformat(_value(manifest, data, f"overview.{kind}.to_ts", "datetime"))
            == _WHEN
        )
    assert (
        _value(manifests["get_steps_summary_tool"], overview["steps"], "total", "QuantitativeValue")
        is None
    )
    assert (
        _value(
            manifests["get_heart_rate_summary_tool"],
            overview["heart_rate"],
            "avg",
            "QuantitativeValue",
        )
        is None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("detail", [False, True])
async def test_incident_handles_resolve_in_the_actual_list_and_detail_modes(
    manifests: dict[str, ToolManifest], monkeypatch: pytest.MonkeyPatch, detail: bool
) -> None:
    incident = Incident(
        id=_ID,
        correlation_key="RedisDown",
        source="alert",
        severity="critical",
        status="open",
        title="Redis down",
        opened_at=_WHEN,
        last_seen_at=_WHEN,
        evidence={},
        diagnosis=None,
        action_log=[],
    )
    repo = MagicMock()
    repo.get_incident = AsyncMock(return_value=incident)
    repo.list_incidents = AsyncMock(return_value=([incident], 1))

    @asynccontextmanager
    async def database() -> Any:
        yield MagicMock()

    monkeypatch.setattr(diagnostics_tools, "user_is_superuser", AsyncMock(return_value=True))
    monkeypatch.setattr(diagnostics_tools, "get_db_context", database)
    monkeypatch.setattr(diagnostics_tools, "DiagnosticsRepository", lambda _: repo)
    runtime = make_tool_runtime(user_id=_ID, thread_id="semantic", store=MagicMock())
    output = await diagnostics_tools.platform_incidents_tool.coroutine(
        incident_id=str(_ID) if detail else "", runtime=runtime
    )
    data = completed_step(output)
    manifest = manifests["platform_incidents_tool"]
    prefix = "" if detail else "incidents[]."
    assert _value(manifest, data, prefix + "id", "incident_id") == str(_ID)
    assert datetime.fromisoformat(_value(manifest, data, prefix + "opened_at", "datetime")) == _WHEN
    if detail:
        assert _value(manifest, data, "last_seen_at", "datetime") == _WHEN.isoformat()
        assert data["diagnosis"] is None
    assert all(field.nullable for field in manifest.outputs)


@pytest.mark.asyncio
async def test_devops_approved_output_exposes_a_distinct_resume_handle(
    manifests: dict[str, ToolManifest], monkeypatch: pytest.MonkeyPatch
) -> None:
    service = MagicMock()
    service.execute_claude_task = AsyncMock(
        return_value=DevOpsTaskResult(success=True, output="Healthy", session_id="cli-session")
    )
    monkeypatch.setattr(devops_tools, "_check_user_is_admin", AsyncMock(return_value=True))
    # A configured server exists; the remote process is replaced at the service boundary.
    monkeypatch.setattr(
        devops_tools, "_resolve_server", lambda _: ({"name": "production"}, "production")
    )
    monkeypatch.setattr(devops_tools, "DevOpsService", lambda: service)
    data = await devops_tools.execute_devops_task_draft(
        {"task": "Check health", "resume_session": "cli-session"}, _ID, object()
    )
    manifest = manifests["claude_server_task_tool"]
    assert "result" not in {field.path for field in manifest.outputs}
    assert _value(manifest, data, "output", "Text") == "Healthy"
    assert _value(manifest, data, "session_id", "devops_session_id") == "cli-session"
    assert service.execute_claude_task.call_args.kwargs["resume_session"] == "cli-session"


def test_hue_handle_and_email_self_delivery_route_are_distinct_values(
    manifests: dict[str, ToolManifest],
) -> None:
    output = ListHueLightsTool(
        tool_name="list_hue_lights", operation="list"
    ).format_registry_response(
        {
            "success": True,
            "data": {
                "lights": [
                    {
                        "id": str(_ID),
                        "metadata": {"name": "Bedroom"},
                        "on": {"on": True},
                        "dimming": {"brightness": 42.0},
                    }
                ]
            },
        }
    )
    assert _value(
        manifests["list_hue_lights_tool"], completed_step(output), "hues[].light_id", "hue_light_id"
    ) == str(_ID)
    data = completed_step(_sent("mailbox", message_id="gmail-message"))
    manifest = manifests["send_email_to_me_tool"]
    assert data["sent_to"] == "mailbox"
    assert (
        next(field for field in manifest.outputs if field.path == "sent_to").semantic_type is None
    )
    assert _value(manifest, data, "message_id", "message_id") == "gmail-message"
    assert (
        _value(manifest, completed_step(_sent("account_email")), "message_id", "message_id") is None
    )
