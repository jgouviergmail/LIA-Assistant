"""The dated tasks a calendar draws (ADR-369, lot 5, item 5.5).

Open tasks due over the days shown, from every list: the calendar reads them in one
request, the lists asked a few at a time. A list that could not be read is named and the
others answer; a list read only in part says so (ADR-185); only a read where every list
fails is a refusal.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from src.core.constants import (
    TASK_LISTS_READ_CONCURRENCY,
    WORKBENCH_CALENDAR_WINDOW_MAX_DAYS,
    WORKBENCH_DUE_TASKS_PAGES_MAX,
)
from src.core.exceptions import BaseAPIException, ConnectorAPIError
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import tasks_service
from src.domains.workbench.schemas.tasks import DueTasksQuery

pytestmark = pytest.mark.unit

USER = uuid4()
PARIS = ZoneInfo("Europe/Paris")
DAYS = DueTasksQuery(start=date(2026, 11, 2), end=date(2026, 11, 8))


def _door(client: Any, kind: ConnectorType = ConnectorType.GOOGLE_TASKS) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any, container: Any = None) -> AsyncIterator[ActiveClient]:
        assert user_id == USER
        yield ActiveClient(client=client, connector_type=kind, preferred_name=None)

    return patch.object(tasks_service, "open_tool_client", opened)


def _down() -> ConnectorAPIError:
    return ConnectorAPIError(connector_type="google_tasks", status_code=503, detail="down")


def _task(task_id: str, due: str | None = "2026-11-03T00:00:00.000Z") -> dict[str, Any]:
    return {"id": task_id, "title": task_id.upper(), **({"due": due} if due else {})}


def _client(pages: dict[str, Any], *, more_lists: bool = False) -> MagicMock:
    """A provider with these lists; a list's answer may be a page, an error or a callable."""

    async def read(list_id: str, **kwargs: Any) -> dict[str, Any]:
        answer = pages[list_id]
        if isinstance(answer, Exception):
            raise answer
        return answer(kwargs) if callable(answer) else answer

    lists = {
        "items": [{"id": list_id, "title": list_id} for list_id in pages],
        "next_page_token": "next" if more_lists else None,
    }
    return MagicMock(
        list_task_lists=AsyncMock(return_value=lists), list_tasks=AsyncMock(side_effect=read)
    )


class TestWhatIsDrawn:
    async def test_every_list_gives_its_open_tasks_due_over_the_days_in_time_order(self) -> None:
        client = _client(
            {
                "home": {
                    "items": [
                        _task("late", "2026-11-07T00:00:00.000Z"),
                        _task("undated", None),
                        _task("before", "2026-11-01T00:00:00.000Z"),
                    ]
                },
                "work": {
                    "items": [
                        _task("soon", "2026-11-02T00:00:00.000Z"),
                        _task("after", "2026-11-09T00:00:00.000Z"),
                    ]
                },
            }
        )

        with _door(client):
            due = await tasks_service.read_due_tasks(USER, PARIS, DAYS)

        assert [(task.id, task.list_id, task.due) for task in due.tasks] == [
            ("soon", "work", date(2026, 11, 2)),
            ("late", "home", date(2026, 11, 7)),
        ]
        assert due.truncated is False
        assert due.failed == []

    async def test_a_task_due_on_the_last_day_shown_is_drawn(self) -> None:
        client = _client({"home": {"items": [_task("last", "2026-11-08T00:00:00.000Z")]}})

        with _door(client):
            due = await tasks_service.read_due_tasks(USER, PARIS, DAYS)

        assert [task.id for task in due.tasks] == ["last"]

    async def test_a_day_is_the_accounts_on_to_do(self) -> None:
        """To Do keeps the instant of local midnight: read in UTC, it lands a day early."""
        client = _client({"home": {"items": [_task("t1", "2026-11-01T23:00:00Z")]}})

        with _door(client, ConnectorType.MICROSOFT_TASKS):
            due = await tasks_service.read_due_tasks(USER, PARIS, DAYS)

        assert [task.due for task in due.tasks] == [date(2026, 11, 2)]

    async def test_what_is_done_is_not_asked(self) -> None:
        client = _client({"home": {"items": []}})

        with _door(client):
            await tasks_service.read_due_tasks(USER, PARIS, DAYS)

        kwargs = client.list_tasks.await_args.kwargs
        assert kwargs["show_completed"] is False
        assert kwargs["show_hidden"] is False

    async def test_no_list_is_nothing_due(self) -> None:
        with _door(_client({})):
            due = await tasks_service.read_due_tasks(USER, PARIS, DAYS)

        assert due.tasks == []
        assert due.failed == []


class TestWhatIsSaid:
    async def test_a_list_that_fails_is_named_and_the_others_answer(self) -> None:
        client = _client(
            {
                "home": _down(),
                "work": {"items": [_task("t1")]},
            }
        )

        with _door(client):
            due = await tasks_service.read_due_tasks(USER, PARIS, DAYS)

        assert [task.id for task in due.tasks] == ["t1"]
        assert due.failed == ["home"]

    async def test_a_read_where_every_list_fails_is_the_refusal(self) -> None:
        client = _client({"home": _down(), "work": _down()})

        with _door(client), pytest.raises(BaseAPIException):
            await tasks_service.read_due_tasks(USER, PARIS, DAYS)

    async def test_a_list_read_in_part_says_so_at_its_bound(self) -> None:
        def endless(kwargs: dict[str, Any]) -> dict[str, Any]:
            return {"items": [_task("t1")], "next_page_token": "more"}

        client = _client({"home": endless})

        with _door(client):
            due = await tasks_service.read_due_tasks(USER, PARIS, DAYS)

        assert client.list_tasks.await_count == WORKBENCH_DUE_TASKS_PAGES_MAX
        assert due.truncated is True

    async def test_each_page_follows_the_token_of_the_one_before(self) -> None:
        def paged(kwargs: dict[str, Any]) -> dict[str, Any]:
            if kwargs["page_token"] is None:
                return {"items": [_task("first")], "next_page_token": "p2"}
            return {"items": [_task("second")], "next_page_token": None}

        client = _client({"home": paged})

        with _door(client):
            due = await tasks_service.read_due_tasks(USER, PARIS, DAYS)

        assert {task.id for task in due.tasks} == {"first", "second"}
        assert due.truncated is False

    async def test_lists_beyond_the_first_page_are_a_cut(self) -> None:
        client = _client({"home": {"items": []}}, more_lists=True)

        with _door(client):
            due = await tasks_service.read_due_tasks(USER, PARIS, DAYS)

        assert due.truncated is True


class TestTheLoad:
    async def test_lists_are_read_a_few_at_a_time(self) -> None:
        running = 0
        peak = 0

        async def read(list_id: str, **kwargs: Any) -> dict[str, Any]:
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            running -= 1
            return {"items": []}

        lists = {"items": [{"id": f"l{index}", "title": "x"} for index in range(12)]}
        client = MagicMock(
            list_task_lists=AsyncMock(return_value=lists), list_tasks=AsyncMock(side_effect=read)
        )

        with _door(client):
            await tasks_service.read_due_tasks(USER, PARIS, DAYS)

        assert 1 < peak <= TASK_LISTS_READ_CONCURRENCY


class TestTheDays:
    def test_they_are_bounded_as_a_calendar_view_is(self) -> None:
        with pytest.raises(ValidationError):
            DueTasksQuery(start=date(2026, 11, 3), end=date(2026, 11, 2))

        first = date(2026, 1, 1)
        with pytest.raises(ValidationError):
            DueTasksQuery(start=first, end=date(2030, 1, 1))
        assert WORKBENCH_CALENDAR_WINDOW_MAX_DAYS < 4 * 365
