"""Business oracles for native cross-domain references, without a model or network.

These are deterministic component simulations. The native manifests, builders,
validator, reference executor and draft preparation are real; external reads
are replaced only where a consumer would fetch preferences or contact records.
"""

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from src.core.context import request_tool_manifests_ctx
from src.core.validators import validate_email
from src.domains.agents.orchestration.parallel_executor import _resolve_step_references
from src.domains.agents.orchestration.plan_schemas import ExecutionStep, StepType
from src.domains.agents.orchestration.validator import PlanValidator, ValidationContext
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.registry.semantic_inventory import collect_static_manifests
from src.domains.agents.semantic.expansion_service import generate_linking_hints_for_plan
from src.domains.agents.tools import runtime_helpers, tasks_tools, weather_dates
from src.domains.agents.tools.base import _current_runtime
from src.domains.agents.tools.calendar_tools import CreateEventDraftTool
from src.domains.agents.tools.emails_tools import SendEmailDraftTool
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.routes_formatting import _format_route_response
from src.domains.agents.tools.tasks_tools import CreateTaskDraftTool
from src.domains.connectors.clients.google_routes_client import TravelMode
from tests.helpers.runtime_context import make_tool_runtime
from tests.unit.domains.agents.registry.reference_harness import completed_step

pytestmark = pytest.mark.unit
_USER = UUID("11111111-2222-3333-4444-555555555555")


@pytest.fixture(scope="module")
def contracts() -> dict[str, ToolManifest]:
    return {manifest.name: manifest for manifest in collect_static_manifests()}


@contextmanager
def _available(contracts: dict[str, ToolManifest]) -> Iterator[None]:
    token = request_tool_manifests_ctx.set(list(contracts.values()))
    try:
        yield
    finally:
        request_tool_manifests_ctx.reset(token)


def _proposal(
    contracts: dict[str, ToolManifest], source: str, consumer: str, parameter: str
) -> object:
    with _available(contracts):
        hints = generate_linking_hints_for_plan(
            [
                {"step_id": "source", "tool_name": source},
                {"step_id": "consumer", "tool_name": consumer},
            ]
        )
    proposal = hints[f"consumer.{parameter}"][0]
    # Array construction is published as JSON syntax, not a scalar address.
    value: object = json.loads(proposal) if proposal.startswith("[") else proposal
    return value


def _arguments(
    contracts: dict[str, ToolManifest],
    consumer: str,
    arguments: dict[str, object],
    output: UnifiedToolOutput,
) -> dict[str, object]:
    manifest = contracts[consumer]
    step = ExecutionStep(
        step_id="consumer",
        step_type=StepType.TOOL,
        tool_name=consumer,
        agent_name=manifest.agent,
        depends_on=["source"],
        parameters=arguments,
    )
    resolved, failure = _resolve_step_references(
        step, {"source": completed_step(output)}, None, time.time(), 1
    )
    assert failure is None and resolved is not None
    registry = AgentRegistry()
    registry.register_tool_manifest(manifest)
    verdict = PlanValidator(registry).validate_plan(
        {"steps": [{"tool": consumer, "args": resolved}]},
        ValidationContext(
            user_id=str(_USER),
            session_id="simulation",
            available_scopes=manifest.permissions.required_scopes,
        ),
    )
    assert verdict.is_valid, verdict.errors
    return dict(resolved)


@contextmanager
def _runtime() -> Iterator[None]:
    token = _current_runtime.set(
        make_tool_runtime(user_id=_USER, thread_id="simulation", store=MagicMock())
    )
    try:
        yield
    finally:
        _current_runtime.reset(token)


async def _calendar_draft(arguments: dict[str, object]) -> dict[str, object]:
    with _runtime():
        result = await CreateEventDraftTool().execute_api_call(MagicMock(), _USER, **arguments)
    return dict(result)


def _timing() -> dict[str, object]:
    return {
        "summary": "Contract review",
        "start_datetime": "2026-10-07T15:00:00",
        "end_datetime": "2026-10-07T16:00:00",
        "timezone": "Europe/Paris",
    }


@pytest.mark.asyncio
async def test_contact_address_reaches_native_mail_and_calendar_without_name_lookup(
    contracts: dict[str, ToolManifest], monkeypatch: pytest.MonkeyPatch
) -> None:
    lookup = AsyncMock(side_effect=AssertionError("A known address needs no contact lookup"))
    monkeypatch.setattr(runtime_helpers, "resolve_contact_to_email", lookup)
    contact = ToolOutputMixin().build_contacts_output(
        [{"resourceName": "people/ada", "emailAddresses": [{"value": "ada@example.com"}]}]
    )
    mail_args = _arguments(
        contracts,
        "send_email_tool",
        {
            "to": _proposal(contracts, "get_contacts_tool", "send_email_tool", "to"),
            "subject": "Review",
            "body": "Ready",
        },
        contact,
    )
    mail = await SendEmailDraftTool().execute_api_call(MagicMock(), _USER, **mail_args)
    assert mail["to"] == "ada@example.com"
    event_args = _arguments(
        contracts,
        "create_event_tool",
        {
            **_timing(),
            "attendees": _proposal(
                contracts, "get_contacts_tool", "create_event_tool", "attendees"
            ),
        },
        contact,
    )
    event = await _calendar_draft(event_args)
    assert event["attendees"] == ["ada@example.com"]
    lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_mail_sender_header_is_projected_to_a_plain_calendar_address(
    contracts: dict[str, ToolManifest], monkeypatch: pytest.MonkeyPatch
) -> None:
    lookup = AsyncMock(side_effect=AssertionError("The sender address is already known"))
    monkeypatch.setattr(runtime_helpers, "resolve_contact_to_email", lookup)
    mail = ToolOutputMixin().build_emails_output(
        [
            {
                "id": "message-a",
                "from": '"Doe, Ada" <ada@example.com>',
                "subject": "Review",
                "body": "Ready",
            }
        ]
    )
    args = _arguments(
        contracts,
        "create_event_tool",
        {
            **_timing(),
            "attendees": _proposal(contracts, "get_emails_tool", "create_event_tool", "attendees"),
        },
        mail,
    )
    assert args["attendees"] == ["ada@example.com"]
    event = await _calendar_draft(args)
    assert event["attendees"] == ["ada@example.com"]
    payload = completed_step(mail)["emails"][0]
    assert payload["from"] == '"Doe, Ada" <ada@example.com>'
    assert validate_email(payload["from_email"])
    lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_file_owner_address_becomes_an_event_attendee(
    contracts: dict[str, ToolManifest], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        runtime_helpers,
        "resolve_contact_to_email",
        AsyncMock(side_effect=AssertionError("No name lookup")),
    )
    document = ToolOutputMixin().build_files_output(
        [
            {
                "id": "drive-a",
                "name": "Review.pdf",
                "owners": [{"displayName": "Ada", "emailAddress": "ada@example.com"}],
            }
        ]
    )
    args = _arguments(
        contracts,
        "create_event_tool",
        {
            **_timing(),
            "attendees": _proposal(contracts, "get_files_tool", "create_event_tool", "attendees"),
        },
        document,
    )
    assert (await _calendar_draft(args))["attendees"] == ["ada@example.com"]


@pytest.mark.asyncio
async def test_explicit_mail_subject_and_body_survive_task_draft_preparation(
    contracts: dict[str, ToolManifest], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tasks_tools, "_resolve_default_task_list", AsyncMock(return_value="list-a"))
    mail = ToolOutputMixin().build_emails_output(
        [
            {
                "id": "message-a",
                "subject": "Review contract",
                "body": "Check section 3",
                "from": "ada@example.com",
            }
        ]
    )
    args = _arguments(
        contracts,
        "create_task_tool",
        {"title": "$steps.source.emails[0].subject", "notes": "$steps.source.emails[0].body"},
        mail,
    )
    draft = await CreateTaskDraftTool().execute_api_call(MagicMock(), _USER, **args)
    assert draft["title"] == "Review contract" and draft["notes"] == "Check section 3"


def test_calendar_location_and_instant_feed_routes_and_forecast_without_unit_drift(
    contracts: dict[str, ToolManifest],
) -> None:
    provider_instant = "2026-10-07T09:00:00-04:00"
    event = ToolOutputMixin().build_events_output(
        [
            {
                "id": "event-a",
                "location": "10 rue de Rivoli, Paris",
                "start": {"dateTime": provider_instant, "timeZone": "America/New_York"},
                "end": {"dateTime": "2026-10-07T10:00:00-04:00"},
            }
        ],
        user_timezone="Europe/Paris",
    )
    route_args = _arguments(
        contracts,
        "get_route_tool",
        {
            "destination": _proposal(contracts, "get_events_tool", "get_route_tool", "destination"),
            "arrival_time": _proposal(
                contracts, "get_events_tool", "get_route_tool", "arrival_time"
            ),
        },
        event,
    )
    arrival = route_args["arrival_time"]
    assert isinstance(arrival, str)
    assert datetime.fromisoformat(arrival).astimezone(UTC) == datetime.fromisoformat(
        provider_instant
    ).astimezone(UTC)
    assert route_args["destination"] == "10 rue de Rivoli, Paris"
    weather_args = _arguments(
        contracts,
        "get_weather_forecast_tool",
        {
            "location": _proposal(
                contracts, "get_events_tool", "get_weather_forecast_tool", "location"
            ),
            "date": _proposal(contracts, "get_events_tool", "get_weather_forecast_tool", "date"),
        },
        event,
    )
    forecast_date = weather_args["date"]
    assert isinstance(forecast_date, str)
    assert weather_dates.calculate_target_date(forecast_date, "Europe/Paris")[0] == "2026-10-07"
    route = _format_route_response(
        {
            "routes": [
                {"duration": "300s", "staticDuration": "300s", "distanceMeters": 1000, "legs": []}
            ]
        },
        "Home",
        str(route_args["destination"]),
        TravelMode.DRIVE,
        "fr",
        "Europe/Paris",
        arrival_time_target=arrival,
        is_arrival_based=True,
    )["data"]["route"]
    assert route["duration_minutes"] == 5 and route["distance_km"] == 1.0
    assert datetime.fromisoformat(route["target_arrival_time"]).astimezone(
        UTC
    ) == datetime.fromisoformat(provider_instant).astimezone(UTC)


@pytest.mark.parametrize("sender", ["", "invalid sender", "a@example.com, b@example.com"])
def test_unreadable_sender_never_becomes_a_fake_address(sender: str) -> None:
    mail = ToolOutputMixin().build_emails_output([{"id": "message-a", "from": sender}])
    payload = completed_step(mail)["emails"][0]
    assert payload["from"] == sender and payload["from_email"] is None


def test_attachment_handle_does_not_supply_a_cloud_document_id(
    contracts: dict[str, ToolManifest],
) -> None:
    with _available(contracts):
        hints = generate_linking_hints_for_plan(
            [
                {"step_id": "mail", "tool_name": "get_emails_tool"},
                {"step_id": "document", "tool_name": "read_document_tool"},
            ]
        )
    assert "document.file_id" not in hints


def test_missing_private_owner_is_a_reference_failure_before_calendar_preparation(
    contracts: dict[str, ToolManifest],
) -> None:
    output = ToolOutputMixin().build_files_output(
        [{"id": "drive-a", "name": "Review.pdf", "owners": [{"displayName": "Private owner"}]}]
    )
    reference = _proposal(contracts, "get_files_tool", "create_event_tool", "attendees")
    step = ExecutionStep(
        step_id="event",
        step_type=StepType.TOOL,
        tool_name="create_event_tool",
        agent_name="event_agent",
        depends_on=["source"],
        parameters={**_timing(), "attendees": reference},
    )
    args, failure = _resolve_step_references(
        step, {"source": completed_step(output)}, None, time.time(), 1
    )
    assert args is None and failure is not None and not failure.success


@pytest.mark.parametrize("zone", ["UTC", "Europe/Paris", "America/New_York", "Pacific/Honolulu"])
def test_forecast_civil_date_is_not_reinterpreted_as_a_utc_instant(
    monkeypatch: pytest.MonkeyPatch, zone: str
) -> None:
    monkeypatch.setattr(
        weather_dates, "now_in_timezone", lambda tz: datetime(2026, 10, 6, 12, tzinfo=ZoneInfo(tz))
    )
    assert weather_dates.calculate_target_date("2026-10-07", zone) == ("2026-10-07", 1, True)
    # Unlike a civil date, an explicit UTC instant must cross the local-day boundary.
    if zone == "America/New_York":
        assert weather_dates.calculate_target_date("2026-10-07T01:00:00Z", zone) == (
            "2026-10-06",
            0,
            True,
        )
