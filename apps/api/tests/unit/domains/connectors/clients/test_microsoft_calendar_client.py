"""Unit tests for MicrosoftCalendarClient OData query building.

Regression coverage for the 2026-07 codebase audit (wave 1):
- The free-text ``query`` was interpolated into the OData ``$filter`` string
  without escaping single quotes, so any apostrophe (e.g. "l'anniversaire")
  produced a malformed filter and a Graph API 400 error.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.clients.microsoft_calendar_client import (
    MicrosoftCalendarClient,
)


@pytest.fixture
def client():
    """MicrosoftCalendarClient with mocked credentials and service (no network)."""
    return MicrosoftCalendarClient(
        user_id=uuid4(),
        credentials=MagicMock(),
        connector_service=MagicMock(),
    )


@pytest.mark.unit
async def test_list_events_escapes_apostrophe_in_odata_filter(client):
    """A query containing an apostrophe must double it in the OData literal."""
    with patch.object(
        client, "_make_request", AsyncMock(return_value={"value": []})
    ) as make_request:
        await client.list_events(query="l'anniversaire")

    params = make_request.await_args.args[2]
    assert params["$filter"] == "contains(subject, 'l''anniversaire')"


@pytest.mark.unit
async def test_list_events_plain_query_filter_unchanged(client):
    """A query without apostrophes keeps the same filter as before."""
    with patch.object(
        client, "_make_request", AsyncMock(return_value={"value": []})
    ) as make_request:
        await client.list_events(query="standup")

    params = make_request.await_args.args[2]
    assert params["$filter"] == "contains(subject, 'standup')"


def _graph_event(event_id: str, day: int) -> dict:
    return {
        "id": event_id,
        "subject": f"Event {event_id}",
        "start": {"dateTime": f"2026-11-{day:02d}T09:00:00.0000000", "timeZone": "UTC"},
        "end": {"dateTime": f"2026-11-{day:02d}T10:00:00.0000000", "timeZone": "UTC"},
    }


_WINDOW = {"time_min": "2026-11-01T00:00:00+00:00", "time_max": "2026-11-30T00:00:00+00:00"}


@pytest.mark.unit
async def test_a_window_keeps_its_soonest_events_whatever_the_page_order(client):
    """calendarView orders nothing: a ``$top`` alone kept an arbitrary N of a busy window."""
    pages = [
        {
            "value": [_graph_event("late", 28), _graph_event("mid", 15)],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/calendarView?$skip=2",
        },
        {"value": [_graph_event("early", 2), _graph_event("later", 20)]},
    ]
    with patch.object(client, "_make_request", AsyncMock(side_effect=pages)):
        answer = await client.list_events(**_WINDOW, max_results=2)

    assert [event["id"] for event in answer["items"]] == ["early", "mid"]
    assert answer["truncated"] is True


@pytest.mark.unit
async def test_a_whole_window_within_the_answer_says_no_cut(client):
    with patch.object(
        client, "_make_request", AsyncMock(return_value={"value": [_graph_event("a", 3)]})
    ):
        answer = await client.list_events(**_WINDOW, max_results=5)

    assert [event["id"] for event in answer["items"]] == ["a"]
    assert answer["truncated"] is False


@pytest.mark.unit
async def test_a_window_search_stays_filtered_by_graph(client):
    """Matching words over a year locally would read every event of it."""
    with patch.object(
        client, "_make_request", AsyncMock(return_value={"value": []})
    ) as make_request:
        await client.list_events(**_WINDOW, max_results=5, query="l'anniversaire")

    endpoint, params = make_request.await_args.args[1], make_request.await_args.args[2]
    assert endpoint == "/me/calendarView"
    assert params["$filter"] == "contains(subject, 'l''anniversaire')"


@pytest.mark.unit
async def test_the_calendar_listing_says_who_owns_each_and_when_it_holds_more(client):
    """``canShare`` is how Graph says the account owns a calendar; a next link, a cut."""
    page = {
        "value": [
            {"id": "mine", "name": "Trips", "canEdit": True, "canShare": True},
            {"id": "team", "name": "Team", "canEdit": True, "canShare": False},
        ],
        "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/calendars?$skip=2",
    }
    with patch.object(client, "_make_request", AsyncMock(return_value=page)) as make_request:
        listed = await client.list_calendars()

    assert "canShare" in make_request.await_args.args[2]["$select"].split(",")
    assert [item["accessRole"] for item in listed["items"]] == ["owner", "writer"]
    assert listed["truncated"] is True


@pytest.mark.unit
async def test_a_whole_calendar_listing_says_no_cut(client):
    with patch.object(client, "_make_request", AsyncMock(return_value={"value": []})):
        listed = await client.list_calendars()

    assert listed == {"items": [], "truncated": False}
