"""Who organised an event, in one word on the three calendars (ADR-369, lot 14).

Google says ``organizer.self``. Graph says ``isOrganizer`` on the event, and iCloud says nothing:
its server knows the account by addresses, read once. Absent keys stay absent.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.clients.apple_calendar_client import AppleCalendarClient
from src.domains.connectors.clients.normalizers.microsoft_calendar_normalizer import (
    normalize_graph_event,
)

pytestmark = pytest.mark.unit


def _graph(**fields: Any) -> dict[str, Any]:
    return {
        "id": "e1",
        "subject": "Review",
        "start": {"dateTime": "2026-11-05T09:00:00", "timeZone": "UTC"},
        "end": {"dateTime": "2026-11-05T10:00:00", "timeZone": "UTC"},
        "organizer": {"emailAddress": {"address": "me@x.org", "name": "Me"}},
        **fields,
    }


class TestOutlook:
    def test_the_person_organising_it_is_said_in_google_s_word(self) -> None:
        assert normalize_graph_event(_graph(isOrganizer=True))["organizer"]["self"] is True

    def test_someone_else_organising_it_claims_nothing(self) -> None:
        assert "self" not in normalize_graph_event(_graph(isOrganizer=False))["organizer"]

    def test_an_event_naming_no_organiser_stays_empty(self) -> None:
        assert normalize_graph_event(_graph(organizer={}, isOrganizer=True))["organizer"] == {}


def _apple(known: Any) -> AppleCalendarClient:
    client = AppleCalendarClient.__new__(AppleCalendarClient)
    client.user_id = uuid4()
    client.credentials = MagicMock(apple_id="me@icloud.com")
    principal = MagicMock(calendar_user_address_set=AsyncMock(side_effect=known))
    client._get_principal = AsyncMock(return_value=principal)  # type: ignore[method-assign]
    client._known_addresses = None
    return client


async def _window(client: AppleCalendarClient, events: list[dict[str, Any]]) -> list[Any]:
    calendar = MagicMock(search=AsyncMock(return_value=events))
    client._get_calendar = AsyncMock(return_value=calendar)  # type: ignore[method-assign]
    with patch(
        "src.domains.connectors.clients.apple_calendar_client.normalize_vevent",
        side_effect=lambda event: event,
    ):
        answer = await client._events_window_impl(
            "cal", "2026-11-01T00:00:00+00:00", "2026-11-02T00:00:00+00:00", 10
        )
    return answer["events"]


def _event(event_id: str, organizer: str | None) -> dict[str, Any]:
    event: dict[str, Any] = {
        "id": event_id,
        "start": {"dateTime": "2026-11-01T09:00:00+00:00"},
    }
    if organizer is not None:
        event["organizer"] = {"email": organizer}
    return event


class TestICloud:
    async def test_the_address_the_server_knows_the_account_by_is_the_person(self) -> None:
        client = _apple(lambda: ["mailto:Alias@Me.com"])

        events = await _window(client, [_event("e1", "alias@me.com")])

        assert events[0]["organizer"]["self"] is True

    async def test_the_sign_in_is_an_address_of_the_person(self) -> None:
        events = await _window(_apple(lambda: []), [_event("e1", "ME@icloud.com")])

        assert events[0]["organizer"]["self"] is True

    async def test_someone_else_claims_nothing(self) -> None:
        events = await _window(_apple(lambda: []), [_event("e1", "ana@x.org")])

        assert "self" not in events[0]["organizer"]

    async def test_a_calendar_with_no_organiser_asks_the_server_nothing(self) -> None:
        client = _apple(lambda: [])

        await _window(client, [_event("e1", None)])

        client._get_principal.assert_not_awaited()

    async def test_the_addresses_are_read_once_for_a_whole_walk(self) -> None:
        client = _apple(lambda: [])

        await _window(client, [_event("e1", "ana@x.org")])
        await _window(client, [_event("e2", "bo@x.org")])

        client._get_principal.assert_awaited_once()

    async def test_a_server_that_will_not_say_leaves_the_sign_in(self) -> None:
        client = _apple(ValueError("no such property"))

        events = await _window(client, [_event("e1", "me@icloud.com")])

        assert events[0]["organizer"]["self"] is True
