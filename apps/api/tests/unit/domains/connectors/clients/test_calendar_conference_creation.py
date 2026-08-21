"""Conference-link creation contract of the calendar clients (lot A, 2026-08).

"Book a 30-min call with Marc" must produce an event WITH a video link when
asked. Provider parity (CLAUDE.md):

- Google: ``conferenceData.createRequest`` (Meet) + ``conferenceDataVersion=1``;
- Microsoft: ``isOnlineMeeting`` + ``onlineMeetingProvider`` (Teams), and the
  Graph normalizer must surface the join URL in the Google shape the event
  card already renders (``conferenceData.entryPoints`` / ``hangoutLink``);
- Apple: CalDAV has no conference concept — the flag is accepted and ignored
  (graceful degradation), never an error.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.connectors.clients.google_calendar_client import GoogleCalendarClient
from src.domains.connectors.clients.microsoft_calendar_client import MicrosoftCalendarClient
from src.domains.connectors.clients.normalizers.microsoft_calendar_normalizer import (
    normalize_graph_event,
)

pytestmark = pytest.mark.unit

_EVENT_ARGS: dict[str, Any] = {
    "summary": "Point avec Marc",
    "start_datetime": "2026-08-27T10:00:00",
    "end_datetime": "2026-08-27T10:30:00",
    "timezone": "Europe/Paris",
}


def _google_client() -> GoogleCalendarClient:
    client = GoogleCalendarClient.__new__(GoogleCalendarClient)
    client.user_id = uuid4()
    return client


def _microsoft_client() -> MicrosoftCalendarClient:
    client = MicrosoftCalendarClient.__new__(MicrosoftCalendarClient)
    client.user_id = uuid4()
    return client


class TestGoogleMeetCreation:
    async def test_add_conference_builds_create_request_and_version_param(self) -> None:
        client = _google_client()
        spy = AsyncMock(return_value={"id": "evt-1"})
        client._make_request = spy  # type: ignore[method-assign]

        await client.create_event(**_EVENT_ARGS, add_conference=True)

        body = spy.call_args.kwargs["json_data"]
        create_request = body["conferenceData"]["createRequest"]
        assert create_request["conferenceSolutionKey"]["type"] == "hangoutsMeet"
        assert create_request["requestId"]
        assert spy.call_args.kwargs["params"] == {"conferenceDataVersion": 1}

    async def test_request_ids_are_unique_per_event(self) -> None:
        """Google dedupes conference creation by requestId — reusing one would
        silently attach the SAME meeting to different events."""
        client = _google_client()
        spy = AsyncMock(return_value={"id": "evt-1"})
        client._make_request = spy  # type: ignore[method-assign]

        await client.create_event(**_EVENT_ARGS, add_conference=True)
        first = spy.call_args.kwargs["json_data"]["conferenceData"]["createRequest"]["requestId"]
        await client.create_event(**_EVENT_ARGS, add_conference=True)
        second = spy.call_args.kwargs["json_data"]["conferenceData"]["createRequest"]["requestId"]
        assert first != second

    async def test_without_flag_no_conference_payload(self) -> None:
        client = _google_client()
        spy = AsyncMock(return_value={"id": "evt-1"})
        client._make_request = spy  # type: ignore[method-assign]

        await client.create_event(**_EVENT_ARGS)

        assert "conferenceData" not in spy.call_args.kwargs["json_data"]
        assert spy.call_args.kwargs.get("params") is None


class TestMicrosoftTeamsCreation:
    async def test_add_conference_sets_online_meeting_fields(self) -> None:
        client = _microsoft_client()
        spy = AsyncMock(return_value={"id": "evt-1", "subject": "Point avec Marc"})
        client._make_request = spy  # type: ignore[method-assign]

        await client.create_event(**_EVENT_ARGS, add_conference=True)

        body = spy.call_args.kwargs["json_data"]
        assert body["isOnlineMeeting"] is True
        assert body["onlineMeetingProvider"] == "teamsForBusiness"

    async def test_without_flag_no_online_meeting_fields(self) -> None:
        client = _microsoft_client()
        spy = AsyncMock(return_value={"id": "evt-1", "subject": "Point avec Marc"})
        client._make_request = spy  # type: ignore[method-assign]

        await client.create_event(**_EVENT_ARGS)

        body = spy.call_args.kwargs["json_data"]
        assert "isOnlineMeeting" not in body


class TestGraphNormalizerConferenceParity:
    def test_online_meeting_join_url_maps_to_google_conference_shape(self) -> None:
        """The event card reads conferenceData.entryPoints[type=video].uri —
        a Teams event must reach it through the same shape as a Meet event."""
        normalized = normalize_graph_event(
            {
                "id": "evt-1",
                "subject": "Point",
                "isOnlineMeeting": True,
                "onlineMeeting": {"joinUrl": "https://teams.microsoft.com/l/meetup-join/xyz"},
            }
        )
        entry_points = normalized["conferenceData"]["entryPoints"]
        video = [ep for ep in entry_points if ep["entryPointType"] == "video"]
        assert video and video[0]["uri"] == "https://teams.microsoft.com/l/meetup-join/xyz"
        assert normalized["hangoutLink"] == "https://teams.microsoft.com/l/meetup-join/xyz"

    def test_event_without_online_meeting_has_no_conference_keys(self) -> None:
        normalized = normalize_graph_event({"id": "evt-1", "subject": "Point"})
        assert "conferenceData" not in normalized
        assert "hangoutLink" not in normalized


class TestAppleGracefulDegradation:
    async def test_add_conference_is_accepted_and_ignored(self) -> None:
        from src.domains.connectors.clients.apple_calendar_client import AppleCalendarClient

        client = AppleCalendarClient.__new__(AppleCalendarClient)
        client.user_id = uuid4()
        executed: dict[str, Any] = {}

        async def fake_execute(operation: str, impl: Any, *args: Any) -> dict[str, Any]:
            executed["operation"] = operation
            executed["args"] = args
            return {"id": "apple-evt-1"}

        client._execute_with_retry = fake_execute  # type: ignore[method-assign]

        result = await client.create_event(**_EVENT_ARGS, add_conference=True)

        assert result["id"] == "apple-evt-1"
        assert executed["operation"] == "create_event"
        # The flag never reaches the CalDAV impl (no conference concept there).
        assert True not in executed["args"]
