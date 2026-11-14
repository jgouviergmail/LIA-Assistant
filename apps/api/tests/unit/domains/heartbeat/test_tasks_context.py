"""The heartbeat's pending tasks: every list of the account, the most pressing first (2026-11-10).

The list the connector's settings name as the default is where a NEW task goes; the decision
reads them all. A list that failed leaves the others to answer; nothing beside a failed list is
that failure, so the source reads ``failed`` and never « no task ».
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest

from src.core.constants import HEARTBEAT_CONTEXT_TASKS_MAX, TASK_LISTS_READ_MAX
from src.core.field_names import FIELD_TASK_LIST_NAME
from src.domains.connectors.active_client import ActiveClient, ClientUnavailable
from src.domains.heartbeat import tasks_context
from src.domains.heartbeat.schemas import HeartbeatContext
from src.domains.heartbeat.tasks_context import (
    due_label,
    fetch_tasks_context,
    is_task_overdue,
    pending_tasks_context,
)

pytestmark = pytest.mark.unit

PARIS_ZONE = ZoneInfo("Europe/Paris")
NEW_YORK_ZONE = ZoneInfo("America/New_York")
USER = uuid4()
_SETTINGS = SimpleNamespace(heartbeat_context_tasks_days=2)
_ACCOUNT = SimpleNamespace(timezone="Europe/Paris")


def _day(offset: int) -> str:
    """A Google due, ``offset`` days from today on the person's clock."""
    day = datetime.now(PARIS_ZONE).date() + timedelta(days=offset)
    return f"{day.isoformat()}T00:00:00.000Z"


def _task(title: str, due: str | None = None, status: str = "needsAction") -> dict[str, Any]:
    return {"id": title, "title": title, "status": status, **({"due": due} if due else {})}


def _client(pages: dict[str, Any]) -> MagicMock:
    """An account whose lists (``home`` is « HOME ») hold these tasks, or fail."""

    async def read(list_id: str, **_kwargs: Any) -> dict[str, Any]:
        answer = pages[list_id]
        if isinstance(answer, Exception):
            raise answer
        return {"items": [dict(task) for task in answer], "next_page_token": None}

    listed = {"items": [{"id": key, "title": key.upper()} for key in pages]}
    return MagicMock(
        list_tasks=AsyncMock(side_effect=read), list_task_lists=AsyncMock(return_value=listed)
    )


def _door(monkeypatch: pytest.MonkeyPatch, opened: Any) -> list[dict[str, Any]]:
    """Open the shared door on ``opened``; what it was asked with is returned."""
    asked: list[dict[str, Any]] = []

    @contextlib.asynccontextmanager
    async def door(category: str, user_id: Any, **options: Any) -> AsyncIterator[Any]:
        asked.append({"category": category, "user_id": user_id, **options})
        yield opened

    monkeypatch.setattr(tasks_context, "open_active_client", door)
    return asked


async def _fetched(
    monkeypatch: pytest.MonkeyPatch, pages: dict[str, Any]
) -> tuple[list[dict[str, Any]] | None, MagicMock]:
    client = _client(pages)
    _door(monkeypatch, ActiveClient(client=client, connector_type="google", preferred_name=None))
    return await fetch_tasks_context(USER, _ACCOUNT, _SETTINGS), client


class TestEveryList:
    async def test_the_tasks_of_every_list_are_read_the_most_pressing_first(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tasks, client = await _fetched(
            monkeypatch,
            {
                "home": [_task("Later", _day(2))],
                "work": [_task("Late", _day(-3)), _task("Soon", _day(1))],
            },
        )

        assert tasks is not None
        assert [(task["title"], task["list"], task["overdue"]) for task in tasks] == [
            ("Late", "WORK", True),
            ("Soon", "WORK", False),
            ("Later", "HOME", False),
        ]
        client.list_task_lists.assert_awaited_once_with(TASK_LISTS_READ_MAX)
        assert [call.args[0] for call in client.list_tasks.await_args_list] == ["home", "work"]

    async def test_no_default_list_is_asked_for(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The default list is where a new task goes: reading names no container."""
        client = _client({"home": []})
        asked = _door(
            monkeypatch, ActiveClient(client=client, connector_type="google", preferred_name=None)
        )

        await fetch_tasks_context(USER, _ACCOUNT, _SETTINGS)

        assert asked == [{"category": "tasks", "user_id": USER}]

    async def test_each_list_is_asked_what_is_due_within_the_days_the_settings_give(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        before = datetime.now(UTC).replace(microsecond=0)

        _tasks, client = await _fetched(monkeypatch, {"home": []})

        asked = client.list_tasks.await_args.kwargs
        due_max = datetime.strptime(asked["due_max"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        horizon = timedelta(days=_SETTINGS.heartbeat_context_tasks_days)
        assert before + horizon <= due_max <= datetime.now(UTC) + horizon
        assert asked["max_results"] == HEARTBEAT_CONTEXT_TASKS_MAX
        assert asked["show_completed"] is False

    async def test_the_prompt_s_bound_keeps_the_most_pressing_of_all_lists(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        crowd = [_task(f"Home {index}", _day(1)) for index in range(HEARTBEAT_CONTEXT_TASKS_MAX)]

        tasks, _client_ = await _fetched(
            monkeypatch, {"home": crowd, "work": [_task("Late", _day(-1))]}
        )

        assert tasks is not None and len(tasks) == HEARTBEAT_CONTEXT_TASKS_MAX
        assert tasks[0]["title"] == "Late", "another list's late task is not cut by the first list"

    async def test_nothing_pending_is_no_source(self, monkeypatch: pytest.MonkeyPatch) -> None:
        tasks, _client_ = await _fetched(
            monkeypatch, {"home": [], "work": [_task("Done", _day(0), status="completed")]}
        )

        assert tasks is None

    @pytest.mark.parametrize(
        "unavailable", [ClientUnavailable.NO_CONNECTOR, ClientUnavailable.NO_CREDENTIALS]
    )
    async def test_no_usable_provider_is_no_source(
        self, monkeypatch: pytest.MonkeyPatch, unavailable: ClientUnavailable
    ) -> None:
        _door(monkeypatch, unavailable)

        assert await fetch_tasks_context(USER, _ACCOUNT, _SETTINGS) is None


class TestAListThatFails:
    async def test_the_others_answer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        tasks, _client_ = await _fetched(
            monkeypatch, {"home": httpx.ConnectError("down"), "work": [_task("Soon", _day(1))]}
        )

        assert tasks is not None and [task["title"] for task in tasks] == ["Soon"]

    async def test_nothing_beside_it_is_a_failed_source_never_no_task(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with pytest.raises(httpx.ConnectError):
            await _fetched(monkeypatch, {"home": httpx.ConnectError("down"), "work": []})

    async def test_a_defect_is_not_a_list_that_failed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with pytest.raises(KeyError):
            await _fetched(monkeypatch, {"home": KeyError("bug"), "work": [_task("Soon", _day(1))]})


class TestWhatTheDecisionReads:
    TODAY = date(2026, 3, 15)

    def test_only_what_is_still_to_do_and_where_it_lives(self) -> None:
        tasks = [
            {**_task("Pay", "2026-03-14T00:00:00.000Z"), FIELD_TASK_LIST_NAME: "Bills"},
            {**_task("Done", "2026-03-10T00:00:00.000Z", status="completed")},
            {"status": "needsAction"},
        ]

        read = pending_tasks_context(tasks, today=self.TODAY, zone=PARIS_ZONE)

        assert read == [
            {"title": "Pay", "due": "2026-03-14", "overdue": True, "list": "Bills"},
            {"title": "Untitled", "due": "no date", "overdue": False, "list": None},
        ]

    def test_the_prompt_names_the_list_of_a_task_that_has_one(self) -> None:
        context = HeartbeatContext(
            pending_tasks=[
                {"title": "Pay", "due": "2026-03-14", "overdue": True, "list": "Bills"},
                {"title": "Call", "due": "2026-03-16", "overdue": False, "list": None},
            ]
        )

        prompt = context.to_prompt_context()

        assert "  - Pay (due: 2026-03-14, list: Bills) [OVERDUE]" in prompt
        assert "  - Call (due: 2026-03-16)" in prompt


class TestTheDueDay:
    """A Google due is the date it names; a To Do due its instant read in the account's zone."""

    def test_a_google_due_is_its_date_west_of_greenwich_too(self) -> None:
        assert due_label({"due": "2026-03-15T00:00:00.000Z"}, NEW_YORK_ZONE) == "2026-03-15"

    def test_a_to_do_due_is_local_midnight_read_in_the_zone(self) -> None:
        # Midnight in Paris, as To Do answers it: 23:00 UTC the evening before.
        task = {"due": "2026-03-14T23:00:00.000Z", "_provider": "microsoft"}
        assert due_label(task, PARIS_ZONE) == "2026-03-15"

    def test_a_plain_date_is_that_date(self) -> None:
        assert due_label({"due": "2026-03-15"}, PARIS_ZONE) == "2026-03-15"

    @pytest.mark.parametrize("raw", [None, "", "soon"])
    def test_no_readable_due_is_no_date(self, raw: str | None) -> None:
        assert due_label({"due": raw}, PARIS_ZONE) == "no date"


class TestATaskIsOverdue:
    """Overdue once its day has passed on the person's clock, never on the day itself."""

    TODAY = date(2026, 3, 15)

    def test_not_on_its_own_day(self) -> None:
        task = {
            "due": "2026-03-14T23:00:00.000Z",
            "_provider": "microsoft",
            "status": "needsAction",
        }
        assert is_task_overdue(task, self.TODAY, PARIS_ZONE) is False

    def test_once_its_day_has_passed(self) -> None:
        task = {"due": "2026-03-14T00:00:00.000Z", "status": "needsAction"}
        assert is_task_overdue(task, self.TODAY, PARIS_ZONE) is True

    def test_never_once_done_nor_without_a_day(self) -> None:
        done = {"due": "2026-03-01T00:00:00.000Z", "status": "completed"}
        undated = {"status": "needsAction"}
        assert is_task_overdue(done, self.TODAY, PARIS_ZONE) is False
        assert is_task_overdue(undated, self.TODAY, PARIS_ZONE) is False
