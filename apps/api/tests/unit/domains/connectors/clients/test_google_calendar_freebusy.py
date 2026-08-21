"""Google Calendar freeBusy client contract (lot B, 2026-08).

The freeBusy endpoint returns busy ranges ONLY — strictly less data than the
list_events projection availability used before (telephony minimization
doctrine, availability.py). This pins the request shape.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.connectors.clients.google_calendar_client import GoogleCalendarClient

pytestmark = pytest.mark.unit


@pytest.fixture
def client() -> GoogleCalendarClient:
    instance = GoogleCalendarClient.__new__(GoogleCalendarClient)
    instance.user_id = uuid4()
    return instance


class TestQueryFreeBusy:
    async def test_posts_window_and_calendar_items(self, client: GoogleCalendarClient) -> None:
        spy = AsyncMock(return_value={"calendars": {"primary": {"busy": []}}})
        client._make_request = spy  # type: ignore[method-assign]

        result = await client.query_freebusy(
            time_min="2026-08-27T00:00:00Z",
            time_max="2026-08-28T00:00:00Z",
            calendar_ids=["primary", "team@group.calendar.google.com"],
        )

        assert spy.call_args.args[:2] == ("POST", "/freeBusy")
        body = spy.call_args.kwargs["json_data"]
        assert body["timeMin"] == "2026-08-27T00:00:00Z"
        assert body["timeMax"] == "2026-08-28T00:00:00Z"
        assert body["items"] == [
            {"id": "primary"},
            {"id": "team@group.calendar.google.com"},
        ]
        assert result["calendars"]["primary"]["busy"] == []

    async def test_defaults_to_primary_calendar(self, client: GoogleCalendarClient) -> None:
        spy = AsyncMock(return_value={"calendars": {}})
        client._make_request = spy  # type: ignore[method-assign]

        await client.query_freebusy(
            time_min="2026-08-27T00:00:00Z", time_max="2026-08-28T00:00:00Z"
        )

        assert spy.call_args.kwargs["json_data"]["items"] == [{"id": "primary"}]
