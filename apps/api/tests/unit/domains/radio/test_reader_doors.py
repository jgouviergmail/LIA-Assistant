"""The journal's connector readers at their doors: what they ask, what a missing or a refused
connector means, and that no session is held while the provider answers (ADR-304)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest

from src.domains.briefing.exceptions import ConnectorAccessError
from src.domains.connectors.active_client import ActiveClient, ClientUnavailable
from src.domains.connectors.calendar_access import CalendarAccess
from src.domains.radio.personal import MAX_PER_SOURCE, PersonalSource
from src.domains.radio.readers import agenda, sent_mail, tasks

pytestmark = pytest.mark.unit

USER = uuid4()
#: 13:00 UTC, 15:00 on the listener's clock (two hours east).
NOW = datetime(2026, 9, 26, 13, 0, tzinfo=UTC)
TZ = timezone(timedelta(hours=2))


class CalendarClient:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items = items
        self.calls: list[dict[str, Any]] = []

    async def list_events(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"items": self.items}


class TasksClient:
    """An account whose lists hold these tasks, or fail (the radio reads every list)."""

    def __init__(self, lists: dict[str, Any]) -> None:
        self.lists = lists
        self.calls: list[dict[str, Any]] = []

    async def list_task_lists(self, max_results: int) -> dict[str, Any]:
        return {"items": [{"id": key, "title": key.title()} for key in self.lists]}

    async def list_tasks(self, task_list_id: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"task_list_id": task_list_id, **kwargs})
        held = self.lists[task_list_id]
        if isinstance(held, Exception):
            raise held
        return {"items": held}


class MailClient:
    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self.messages = messages
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def search_emails(self, query: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((query, kwargs))
        return {"messages": self.messages}


def _door(opened: object) -> Any:
    @asynccontextmanager
    async def open_it(*_args: object, **_kwargs: object) -> Any:
        yield opened

    return open_it


class TestAgenda:
    async def test_the_done_window_runs_from_local_midnight_to_now_on_the_owner_s_calendar(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = CalendarClient(
            [
                {
                    "id": "e1",
                    "summary": "Dentist",
                    "start": {"dateTime": "2026-09-26T09:30:00+02:00"},
                    "end": {"dateTime": "2026-09-26T10:00:00+02:00"},
                }
            ]
        )
        access = CalendarAccess(client=client, calendar_id="work", connector_type="google")
        monkeypatch.setattr(agenda, "open_active_calendar", _door(access))
        drafts = await agenda.read_agenda_done(USER, now=NOW, tz=TZ)
        [call] = client.calls
        assert call["time_min"] == datetime(2026, 9, 26, 0, 0, tzinfo=TZ).isoformat()
        assert call["time_max"] == NOW.isoformat()
        assert call["calendar_id"] == "work"
        assert [d.key for d in drafts] == ["done:event:e1"]

    async def test_the_week_ahead_runs_from_tomorrow_s_midnight_for_seven_days(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = CalendarClient([])
        access = CalendarAccess(client=client, calendar_id="primary", connector_type="google")
        monkeypatch.setattr(agenda, "open_active_calendar", _door(access))
        assert await agenda.read_agenda_ahead(USER, now=NOW, tz=TZ) == []
        [call] = client.calls
        assert call["time_min"] == datetime(2026, 9, 27, 0, 0, tzinfo=TZ).isoformat()
        assert call["time_max"] == datetime(2026, 10, 4, 0, 0, tzinfo=TZ).isoformat()

    async def test_no_calendar_is_nothing_to_read_but_refused_credentials_are_a_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(agenda, "open_active_calendar", _door(ClientUnavailable.NO_CONNECTOR))
        assert await agenda.read_agenda_done(USER, now=NOW, tz=TZ) == []
        monkeypatch.setattr(agenda, "open_active_calendar", _door(ClientUnavailable.NO_CREDENTIALS))
        with pytest.raises(ConnectorAccessError):
            await agenda.read_agenda_done(USER, now=NOW, tz=TZ)


class TestTasks:
    def active(self, client: TasksClient) -> ActiveClient:
        return ActiveClient(client=client, connector_type="google", preferred_name=None)

    async def test_done_asks_for_the_completed_tasks_and_keeps_today_s(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = TasksClient(
            {
                "home": [
                    {
                        "id": "t1",
                        "title": "Done",
                        "status": "completed",
                        "completed": "2026-09-26T08:00:00.000Z",
                    },
                    {
                        "id": "t2",
                        "title": "Old",
                        "status": "completed",
                        "completed": "2026-09-25T08:00:00.000Z",
                    },
                ],
                "work": [
                    {
                        "id": "t3",
                        "title": "Sent",
                        "status": "completed",
                        "completed": "2026-09-26T09:00:00.000Z",
                    }
                ],
            }
        )
        monkeypatch.setattr(tasks, "open_active_client", _door(self.active(client)))
        drafts = await tasks.read_tasks_done(USER, now=NOW, tz=TZ)
        assert [call["task_list_id"] for call in client.calls] == ["home", "work"]
        for call in client.calls:
            assert (call["show_completed"], call["show_hidden"]) == (True, True)
            assert call["completed_min"] == datetime(2026, 9, 26, 0, 0, tzinfo=TZ).isoformat()
        assert [d.key for d in drafts] == ["done:task:t1", "done:task:t3"], "every list"

    async def test_ahead_asks_for_the_week_s_open_tasks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = TasksClient({"home": []})
        monkeypatch.setattr(tasks, "open_active_client", _door(self.active(client)))
        assert await tasks.read_tasks_ahead(USER, now=NOW, tz=TZ) == []
        [call] = client.calls
        assert call["show_completed"] is False
        assert call["due_min"] == datetime(2026, 9, 27, 0, 0, tzinfo=TZ).isoformat()
        assert call["due_max"] == datetime(2026, 10, 4, 0, 0, tzinfo=TZ).isoformat()

    async def test_the_week_ahead_tells_the_soonest_of_every_list_first(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One list's whole week never hides another list's tomorrow behind the bound."""

        def due(task_id: str, day: int) -> dict[str, Any]:
            return {"id": task_id, "title": task_id, "due": f"2026-09-{day}T00:00:00.000Z"}

        crowd = [due(f"h{index}", 30) for index in range(MAX_PER_SOURCE[PersonalSource.TASKS])]
        client = TasksClient({"home": crowd, "work": [due("w1", 27)]})
        monkeypatch.setattr(tasks, "open_active_client", _door(self.active(client)))

        drafts = await tasks.read_tasks_ahead(USER, now=NOW, tz=TZ)

        assert len(drafts) == MAX_PER_SOURCE[PersonalSource.TASKS]
        assert drafts[0].key == "task:w1"

    async def test_a_list_that_fails_leaves_the_others_to_answer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        done = {
            "id": "t1",
            "title": "Done",
            "status": "completed",
            "completed": "2026-09-26T08:00:00.000Z",
        }
        client = TasksClient({"home": TimeoutError(), "work": [done]})
        monkeypatch.setattr(tasks, "open_active_client", _door(self.active(client)))

        drafts = await tasks.read_tasks_done(USER, now=NOW, tz=TZ)

        assert [d.key for d in drafts] == ["done:task:t1"]

    async def test_nothing_beside_a_failed_list_is_a_failed_read_never_an_empty_day(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = TasksClient({"home": TimeoutError(), "work": []})
        monkeypatch.setattr(tasks, "open_active_client", _door(self.active(client)))

        with pytest.raises(TimeoutError):
            await tasks.read_tasks_done(USER, now=NOW, tz=TZ)

    async def test_no_tasks_provider_is_nothing_to_read(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tasks, "open_active_client", _door(ClientUnavailable.NO_CONNECTOR))
        assert await tasks.read_tasks_done(USER, now=NOW, tz=TZ) == []
        monkeypatch.setattr(tasks, "open_active_client", _door(ClientUnavailable.NO_CREDENTIALS))
        with pytest.raises(ConnectorAccessError):
            await tasks.read_tasks_ahead(USER, now=NOW, tz=TZ)


class TestSentMail:
    async def test_the_sent_folder_is_asked_from_yesterday_headers_only_and_today_kept(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = MailClient(
            [
                {
                    "id": "m1",
                    "to": "Sam",
                    "subject": "Quote",
                    "date": "Sat, 26 Sep 2026 10:12:00 +0200",
                },
                {
                    "id": "m2",
                    "to": "Kim",
                    "subject": "Old",
                    "date": "Fri, 25 Sep 2026 10:12:00 +0200",
                },
            ]
        )
        opened = ActiveClient(client=client, connector_type="google", preferred_name=None)
        monkeypatch.setattr(sent_mail, "open_active_client", _door(opened))
        drafts = await sent_mail.read_sent_mail(USER, now=NOW, tz=TZ)
        [(query, kwargs)] = client.calls
        assert query == "in:sent after:2026/09/25"
        assert kwargs["headers_only"] is True
        assert [d.key for d in drafts] == ["done:email:m1"]

    async def test_no_mailbox_is_nothing_to_read_but_refused_credentials_are_a_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sent_mail, "open_active_client", _door(ClientUnavailable.NO_CONNECTOR))
        assert await sent_mail.read_sent_mail(USER, now=NOW, tz=TZ) == []
        monkeypatch.setattr(
            sent_mail, "open_active_client", _door(ClientUnavailable.NO_CREDENTIALS)
        )
        with pytest.raises(ConnectorAccessError):
            await sent_mail.read_sent_mail(USER, now=NOW, tz=TZ)
