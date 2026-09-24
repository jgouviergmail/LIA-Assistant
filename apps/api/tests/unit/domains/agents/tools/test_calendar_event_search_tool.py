"""The calendar tool searches its window itself, the same way on every provider.

Before: ``query`` was read as a PERSON — a contacts lookup (« déjeuner » logged
``recipient_resolution_failed`` and cost a People API call), the provider was
searched for that person's e-mail, and any other word was dropped without the
model being told, so the window came back as if it were the search result. The
same word also meant three things on three providers (Google everything,
Microsoft the subject, Apple title and description). Now the window is read with
no provider query and filtered by ONE matcher, and the result says what was
searched (measured 2026-09-23 on a real turn).
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import BaseModel

from src.core.config import settings
from src.domains.agents.calendar.catalogue_manifests import get_events_catalogue_manifest
from src.domains.agents.calendar.event_search import QUERY_CONTRACT, SEARCHED_FIELDS
from src.domains.agents.tools import calendar_tools
from src.domains.agents.tools.calendar_tools import SearchEventsTool, get_events_tool
from src.domains.connectors.clients.apple_calendar_client import AppleCalendarClient
from src.domains.connectors.clients.google_calendar_client import GoogleCalendarClient
from src.domains.connectors.clients.microsoft_calendar_client import MicrosoftCalendarClient

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 9, 23, 8, 0, tzinfo=UTC)

LUNCH = {
    "id": "lunch",
    "summary": "Déjeuner en terrasse",
    "start": {"dateTime": "2026-09-24T12:30:00+02:00"},
    "end": {"dateTime": "2026-09-24T14:00:00+02:00"},
    "attendees": [{"email": "alex.li@example.com", "displayName": "Alex Li"}],
}
REVIEW = {
    "id": "review",
    "summary": "Revue de projet",
    "start": {"dateTime": "2026-09-24T09:00:00+02:00"},
    "end": {"dateTime": "2026-09-24T10:00:00+02:00"},
}


def _tool() -> SearchEventsTool:
    tool = SearchEventsTool()
    tool.runtime = MagicMock()
    return tool


def _client(spec: type, items: list[dict[str, Any]]) -> MagicMock:
    client = MagicMock(spec=spec)
    client.list_events = AsyncMock(return_value={"items": items})
    client.connector_service = MagicMock()
    client.connector_type = MagicMock()
    return client


@contextlib.contextmanager
def _turn() -> Any:
    with (
        patch.object(calendar_tools, "now_utc", return_value=_NOW),
        patch.object(
            calendar_tools, "get_user_preferences", new=AsyncMock(return_value=("UTC", "fr", None))
        ),
        patch.object(
            calendar_tools, "resolve_calendar_name", new=AsyncMock(return_value="primary")
        ),
        patch(
            "src.domains.connectors.preferences.owner_defaults.read_owner_preference_name",
            new=AsyncMock(return_value=None),
        ),
    ):
        yield


_CLIENTS = [GoogleCalendarClient, MicrosoftCalendarClient, AppleCalendarClient]


class TestTheWindowIsSearchedHere:
    @pytest.mark.parametrize("spec", _CLIENTS)
    async def test_no_provider_ever_receives_the_query(self, spec: type) -> None:
        client = _client(spec, [LUNCH, REVIEW])

        with _turn():
            await _tool().execute_api_call(client, uuid4(), query="déjeuner")

        kwargs = client.list_events.await_args.kwargs
        assert kwargs["query"] is None
        assert kwargs["max_results"] == settings.api_max_items_per_request

    @pytest.mark.parametrize("spec", _CLIENTS)
    async def test_the_matching_events_are_returned(self, spec: type) -> None:
        client = _client(spec, [LUNCH, REVIEW])

        with _turn():
            result = await _tool().execute_api_call(client, uuid4(), query="Alex")

        assert [event["id"] for event in result["events"]] == ["lunch"]

    async def test_no_contact_is_looked_up(self) -> None:
        client = _client(GoogleCalendarClient, [LUNCH, REVIEW])
        lookup = AsyncMock()

        with (
            _turn(),
            patch("src.domains.agents.tools.runtime_helpers.resolve_contact_to_email", new=lookup),
        ):
            await _tool().execute_api_call(client, uuid4(), query="déjeuner")

        lookup.assert_not_awaited()


class TestTheSearchIsStated:
    async def test_what_was_searched_travels_with_the_result(self) -> None:
        client = _client(GoogleCalendarClient, [LUNCH, REVIEW])

        with _turn():
            result = await _tool().execute_api_call(client, uuid4(), query="Alex")

        assert result["search"] == {
            "query": "Alex",
            "fields": list(SEARCHED_FIELDS),
            "matched": 1,
            "searched": 2,
            "window_complete": True,
        }
        assert result["truncated"] is False

    async def test_a_full_read_says_the_window_may_hold_more(self) -> None:
        window = [{**REVIEW, "id": f"e{i}"} for i in range(settings.api_max_items_per_request)]
        client = _client(GoogleCalendarClient, window)

        with _turn():
            result = await _tool().execute_api_call(client, uuid4(), query="Alex")

        assert result["search"]["window_complete"] is False
        assert result["truncated"] is True

    async def test_matches_past_max_results_are_cut_and_counted(self) -> None:
        window = [{**LUNCH, "id": f"l{i}"} for i in range(5)]
        client = _client(GoogleCalendarClient, window)

        with _turn():
            result = await _tool().execute_api_call(
                client, uuid4(), query="déjeuner", max_results=2
            )

        assert len(result["events"]) == 2
        assert result["search"]["matched"] == 5
        assert result["truncated"] is True

    async def test_the_statement_reaches_the_model(self) -> None:
        client = _client(GoogleCalendarClient, [LUNCH, REVIEW])

        with _turn():
            result = await _tool().execute_api_call(client, uuid4(), query="Alex")
        output = _tool().format_registry_response(result)

        assert output.structured_data["search"]["matched"] == 1
        assert "matching 'Alex'" in output.message

    async def test_no_match_is_said_rather_than_listed(self) -> None:
        client = _client(GoogleCalendarClient, [LUNCH, REVIEW])

        with _turn():
            result = await _tool().execute_api_call(client, uuid4(), query="dentiste")
        output = _tool().format_registry_response(result)

        assert result["events"] == []
        assert "no event matching 'dentiste'" in output.message


class TestOneContract:
    def test_the_planner_reads_the_rule_the_tool_applies(self) -> None:
        query = next(p for p in get_events_catalogue_manifest.parameters if p.name == "query")
        assert query.description == QUERY_CONTRACT

    def test_the_react_loop_reads_the_same_rule(self) -> None:
        schema = get_events_tool.args_schema
        assert isinstance(schema, type) and issubclass(schema, BaseModel)
        assert schema.model_fields["query"].description == QUERY_CONTRACT
