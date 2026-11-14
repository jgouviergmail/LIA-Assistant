"""A home card's item carries what its tool needs to open it (2026-11-07).

A click on an item opens it in the Tools: the agenda names the calendar and the
event (and the video call it holds), the tasks card names each task's REAL
list — an alias such as Google's ``@default`` is unknown to the Tools, and a
task opened under the wrong list would be written to the wrong list. The card
reads every list (2026-11-10), so the ids are the provider's own listing.
"""

from __future__ import annotations

from contextlib import ExitStack, asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from src.domains.briefing.fetchers import fetch_agenda, fetch_tasks
from src.domains.briefing.formatters import format_agenda_event
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.calendar_access import CalendarAccess

PARIS = ZoneInfo("Europe/Paris")
pytestmark = pytest.mark.unit


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4())


def _event(**extra: object) -> dict[str, object]:
    start = datetime.now(UTC) + timedelta(hours=2)
    return {
        "id": "evt-1",
        "summary": "Weekly",
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": (start + timedelta(hours=1)).isoformat()},
        **extra,
    }


class TestAgendaItemAddress:
    def test_a_meet_link_is_the_video_call(self) -> None:
        item = format_agenda_event(_event(hangoutLink="https://meet.google.com/abc"), PARIS, "en")

        assert item.conference_url == "https://meet.google.com/abc"

    def test_a_video_entry_point_is_the_video_call(self) -> None:
        """Graph's Teams link is normalised into a video entry point."""
        raw = _event(
            conferenceData={
                "entryPoints": [
                    {"entryPointType": "phone", "uri": "tel:+33100000000"},
                    {"entryPointType": "video", "uri": "https://teams.microsoft.com/l/x"},
                ]
            }
        )

        item = format_agenda_event(raw, PARIS, "en")

        assert item.conference_url == "https://teams.microsoft.com/l/x"

    @pytest.mark.parametrize("link", ["javascript:alert(1)", "data:text/html,x", "meet", ""])
    def test_only_a_web_address_is_a_video_call(self, link: str) -> None:
        item = format_agenda_event(_event(hangoutLink=link), PARIS, "en")

        assert item.conference_url is None

    async def test_the_card_names_the_calendar_read_and_asks_for_the_call(self) -> None:
        client = MagicMock()
        client.list_events = AsyncMock(
            return_value={"items": [_event(hangoutLink="https://meet.google.com/abc")]}
        )

        @asynccontextmanager
        async def opened(user_id, *, fresh=False):
            yield CalendarAccess(client=client, calendar_id="work@group", connector_type=None)

        with (
            patch("src.domains.connectors.calendar_access.open_active_calendar", opened),
            patch(
                "src.domains.briefing.fetchers.classify_briefing_items",
                AsyncMock(side_effect=lambda items, **_: items),
            ),
        ):
            data = await fetch_agenda(user=_user(), user_tz=PARIS, language="en")

        [item] = data.events
        assert (item.calendar_id, item.id, item.conference_url) == (
            "work@group",
            "evt-1",
            "https://meet.google.com/abc",
        )
        fields = client.list_events.await_args.kwargs["fields"]
        assert {"hangoutLink", "conferenceData"} <= set(fields)


def _tasks_client(lists: list[dict[str, str]]) -> MagicMock:
    """A provider with these lists, each holding one task named after it."""

    async def read(list_id: str, **kwargs: object) -> dict[str, object]:
        return {"items": [{"id": f"t-{list_id}", "title": "Pay", "status": "needsAction"}]}

    client = MagicMock()
    client.list_task_lists = AsyncMock(return_value={"items": lists, "next_page_token": None})
    client.list_tasks = AsyncMock(side_effect=read)
    return client


async def _tasks_card(client: MagicMock):
    @asynccontextmanager
    async def door(category, user_id, *, container=None):
        yield ActiveClient(client=client, connector_type=MagicMock(), preferred_name=None)

    settings = SimpleNamespace(
        briefing_max_tasks_items=5,
        briefing_tasks_horizon_days=7,
        briefing_max_documents_items=5,
    )
    with ExitStack() as stack:
        stack.enter_context(patch("src.domains.connectors.active_client.open_active_client", door))
        stack.enter_context(patch("src.domains.briefing.fetchers.settings", settings))
        return await fetch_tasks(user=_user(), user_tz=PARIS)


class TestTaskItemAddress:
    async def test_each_task_is_named_under_the_list_it_was_read_from(self) -> None:
        """Two lists, two addresses: a task opened under another list than its own
        would be written there."""
        client = _tasks_client(
            [{"id": "MTIzNDU2", "title": "My Tasks"}, {"id": "list-courses", "title": "Courses"}]
        )

        data = await _tasks_card(client)

        assert sorted((item.list_id, item.id, item.list_name) for item in data.items) == [
            ("MTIzNDU2", "t-MTIzNDU2", "My Tasks"),
            ("list-courses", "t-list-courses", "Courses"),
        ]

    async def test_no_alias_is_ever_asked_nor_named(self) -> None:
        """The ids are the provider's own listing: ``@default`` names no list the Tools know."""
        client = _tasks_client([{"id": "MTIzNDU2", "title": "My Tasks"}])

        data = await _tasks_card(client)

        assert [call.args for call in client.list_tasks.await_args_list] == [("MTIzNDU2",)]
        assert [item.list_id for item in data.items] == ["MTIzNDU2"]
        client.get_task_list.assert_not_called()
