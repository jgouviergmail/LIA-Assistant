"""Organising tasks by the person's own hand (ADR-369, lot 9).

Views span every list and are decided in the account's day. An act on a selection answers item
by item. A task moved on To Do comes back under another id, and one left in both lists is said.
Clearing what is done deletes it, on both providers, because Google's own `clear` only hides it
from a listing the screen asks with the hidden ones. What the provider lacks is refused unsent.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from src.core.config import settings
from src.core.constants import WORKBENCH_TASK_UPCOMING_DAYS, WORKBENCH_TASKS_CLEAR_MAX
from src.core.exceptions import BaseAPIException, ConnectorAPIError
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.task_details import TaskDetails, TaskLeftBehindError
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import idempotency, tasks_organize, tasks_service
from src.domains.workbench.errors import (
    INVALID_REQUEST,
    NOT_SUPPORTED_BY_PROVIDER,
    TASK_LEFT_BEHIND,
)
from src.domains.workbench.schemas.tasks import (
    NewTask,
    NewTaskStep,
    TaskChange,
    TaskListRename,
    TaskPlacement,
    TaskSelection,
    TaskSelectionCompletion,
    TaskSelectionMove,
    TaskStepChange,
    TaskViewQuery,
    ViewTasks,
)
from tests.unit.domains.workbench.fakes import FakeRedis

pytestmark = pytest.mark.unit

USER = uuid4()
PARIS = ZoneInfo("Europe/Paris")
GOOGLE, TODO = ConnectorType.GOOGLE_TASKS, ConnectorType.MICROSOFT_TASKS
KEY = uuid4()


@pytest.fixture(autouse=True)
def _redis() -> Any:
    with patch.object(idempotency, "get_redis_cache", AsyncMock(return_value=FakeRedis())):
        yield


def _door(client: Any, kind: ConnectorType = GOOGLE) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any, container: Any = None) -> AsyncIterator[ActiveClient]:
        yield ActiveClient(client=client, connector_type=kind, preferred_name=None)

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(tasks_service, "open_tool_client", opened))
        stack.enter_context(patch.object(tasks_organize, "open_tool_client", opened))
        return stack.pop_all()


def _client(**methods: Any) -> MagicMock:
    return MagicMock(**{name: AsyncMock(return_value=value) for name, value in methods.items()})


def _gone() -> ConnectorAPIError:
    return ConnectorAPIError(connector_type="google_tasks", status_code=404, detail="x")


def _reading(*dues: str | None) -> MagicMock:
    return _client(
        list_task_lists={"items": [{"id": "l1"}], "next_page_token": None},
        list_tasks={
            "items": [
                {"id": f"t{index}", "title": f"T{index}", "due": due}
                for index, due in enumerate(dues)
            ],
            "next_page_token": None,
        },
    )


class TestViews:
    NOW = datetime(2026, 11, 5, 23, 30, tzinfo=UTC)  # Already the 6th in Paris.

    async def _view(self, view: str, client: MagicMock) -> ViewTasks:
        with (
            _door(client),
            patch.object(tasks_service, "now_utc", return_value=self.NOW),
        ):
            return await tasks_service.read_task_view(
                USER, PARIS, TaskViewQuery(view=view)  # type: ignore[arg-type]
            )

    async def _read(self, view: str, client: MagicMock) -> list[date | None]:
        return [task.due for task in (await self._view(view, client)).tasks]

    async def test_today_is_the_account_s_day(self) -> None:
        client = _reading("2026-11-05T00:00:00.000Z", "2026-11-06T00:00:00.000Z")

        assert await self._read("today", client) == [date(2026, 11, 6)]

    async def test_overdue_reaches_as_far_back_as_a_task_goes(self) -> None:
        client = _reading(
            "2019-01-01T00:00:00.000Z", "2026-11-05T00:00:00.000Z", "2026-11-06T00:00:00.000Z"
        )

        assert await self._read("overdue", client) == [date(2019, 1, 1), date(2026, 11, 5)]

    async def test_upcoming_starts_tomorrow_and_stops_at_the_bound(self) -> None:
        last = date.fromordinal(date(2026, 11, 6).toordinal() + WORKBENCH_TASK_UPCOMING_DAYS)
        beyond = date.fromordinal(last.toordinal() + 1)
        client = _reading(
            "2026-11-06T00:00:00.000Z",
            "2026-11-07T00:00:00.000Z",
            f"{last.isoformat()}T00:00:00.000Z",
            f"{beyond.isoformat()}T00:00:00.000Z",
        )

        assert await self._read("upcoming", client) == [date(2026, 11, 7), last]

    async def test_the_timeline_is_the_three_views_together(self) -> None:
        """What is late, today's and the days ahead up to the bound: nothing else, in time order."""
        last = date.fromordinal(date(2026, 11, 6).toordinal() + WORKBENCH_TASK_UPCOMING_DAYS)
        beyond = date.fromordinal(last.toordinal() + 1)
        client = _reading(
            f"{beyond.isoformat()}T00:00:00.000Z",
            f"{last.isoformat()}T00:00:00.000Z",
            None,
            "2026-11-06T00:00:00.000Z",
            "2019-01-01T00:00:00.000Z",
        )

        assert await self._read("timeline", client) == [date(2019, 1, 1), date(2026, 11, 6), last]

    async def test_the_timeline_holds_exactly_what_the_three_views_hold(self) -> None:
        last = date.fromordinal(date(2026, 11, 6).toordinal() + WORKBENCH_TASK_UPCOMING_DAYS)
        dues = [
            "2019-01-01T00:00:00.000Z",
            "2026-11-05T00:00:00.000Z",
            "2026-11-06T00:00:00.000Z",
            "2026-11-07T00:00:00.000Z",
            f"{last.isoformat()}T00:00:00.000Z",
            f"{date.fromordinal(last.toordinal() + 1).isoformat()}T00:00:00.000Z",
            None,
        ]

        apart = [
            day
            for view in ("overdue", "today", "upcoming")
            for day in await self._read(view, _reading(*dues))
        ]

        assert await self._read("timeline", _reading(*dues)) == apart

    async def test_all_gathers_every_open_task_whatever_its_day(self) -> None:
        """Dated ones in time order, however far; the undated after them."""
        client = _reading(None, "2031-05-01T00:00:00.000Z", "2019-01-01T00:00:00.000Z", None)

        found = await self._view("all", client)

        assert [(task.id, task.due) for task in found.tasks] == [
            ("t2", date(2019, 1, 1)),
            ("t1", date(2031, 5, 1)),
            ("t0", None),
            ("t3", None),
        ]

    async def test_all_names_the_list_of_each_task_and_keeps_the_lists_order_undated(self) -> None:
        pages = {
            "home": {"items": [{"id": "h1", "title": "H1"}, {"id": "h2", "title": "H2"}]},
            "work": {
                "items": [
                    {"id": "w1", "title": "W1"},
                    {"id": "w2", "title": "W2", "due": "2026-11-09T00:00:00.000Z"},
                ]
            },
        }
        client = MagicMock(
            list_task_lists=AsyncMock(
                return_value={"items": [{"id": "home"}, {"id": "work"}], "next_page_token": None}
            ),
            list_tasks=AsyncMock(side_effect=lambda list_id, **_: pages[list_id]),
        )

        found = await self._view("all", client)

        assert [(task.list_id, task.id) for task in found.tasks] == [
            ("work", "w2"),
            ("home", "h1"),
            ("home", "h2"),
            ("work", "w1"),
        ]
        assert (found.truncated, found.failed) == (False, [])

    async def test_all_asks_for_what_is_still_to_do_only(self) -> None:
        client = _reading(None)

        await self._view("all", client)

        asked = client.list_tasks.await_args.kwargs
        assert (asked["show_completed"], asked["show_hidden"]) == (False, False)

    async def test_a_view_says_the_list_it_could_not_read(self) -> None:
        down = ConnectorAPIError(connector_type="google_tasks", status_code=503, detail="down")
        pages: dict[str, Any] = {"home": down, "work": {"items": [{"id": "w1", "title": "W1"}]}}

        async def read(list_id: str, **_: Any) -> dict[str, Any]:
            answer = pages[list_id]
            if isinstance(answer, Exception):
                raise answer
            return dict(answer)

        client = MagicMock(
            list_task_lists=AsyncMock(
                return_value={"items": [{"id": "home"}, {"id": "work"}], "next_page_token": "more"}
            ),
            list_tasks=AsyncMock(side_effect=read),
        )

        found = await self._view("all", client)

        assert [task.id for task in found.tasks] == ["w1"]
        assert found.failed == ["home"]
        assert found.truncated is True

    def test_a_view_nobody_named_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            TaskViewQuery(view="someday")  # type: ignore[arg-type]


class TestRenamingAList:
    async def test_it_is_renamed(self) -> None:
        client = _client(rename_task_list={"id": "l1", "title": "New"})

        with _door(client):
            renamed = await tasks_organize.rename_task_list(
                USER, TaskListRename(list_id="l1", title=" New ")
            )

        client.rename_task_list.assert_awaited_once_with("l1", "New")
        assert renamed.title == "New"


class TestASelection:
    async def test_each_task_is_marked_and_answered(self) -> None:
        client = _client()
        client.update_task = AsyncMock(side_effect=[{"id": "t1"}, _gone()])

        with _door(client):
            outcome = await tasks_organize.set_completed(
                USER,
                TaskSelectionCompletion(list_id="l1", task_ids=["t1", "t2"], completed=True),
            )

        assert outcome.done == ["t1"]
        assert [(item.id, item.status) for item in outcome.failed] == [("t2", "not_found")]
        assert client.update_task.await_args_list[0].kwargs["status"] == "completed"

    async def test_reopening_asks_for_it(self) -> None:
        client = _client(update_task={"id": "t1"})

        with _door(client):
            await tasks_organize.set_completed(
                USER, TaskSelectionCompletion(list_id="l1", task_ids=["t1"], completed=False)
            )

        assert client.update_task.await_args.kwargs["status"] == "needsAction"

    async def test_each_task_is_deleted_and_one_already_gone_counts_as_gone(self) -> None:
        client = _client()
        client.delete_task = AsyncMock(side_effect=[True, _gone()])

        with _door(client):
            outcome = await tasks_organize.delete_tasks(
                USER, TaskSelection(list_id="l1", task_ids=["t1", "t2"])
            )

        assert outcome.done == ["t1"]
        assert outcome.failed[0].status == "not_found"

    def test_a_selection_stays_within_the_bound(self) -> None:
        too_many = [f"t{index}" for index in range(settings.workbench_bulk_max_items + 1)]

        with pytest.raises(ValidationError):
            TaskSelection(list_id="l1", task_ids=too_many)


class TestMoving:
    REQUEST = TaskSelectionMove(list_id="l1", task_ids=["t1"], destination_list_id="l2")

    async def test_each_task_says_what_it_is_called_now(self) -> None:
        client = _client(move_task={"id": "n1"})

        with _door(client, TODO):
            outcome = await tasks_organize.move_tasks(USER, self.REQUEST)

        client.move_task.assert_awaited_once_with("l1", "t1", "l2")
        assert outcome.done == ["t1"]
        assert [(item.id, item.new_id) for item in outcome.moved] == [("t1", "n1")]

    async def test_a_task_left_in_both_lists_is_said(self) -> None:
        client = _client()
        client.move_task = AsyncMock(side_effect=TaskLeftBehindError)

        with _door(client, TODO):
            outcome = await tasks_organize.move_tasks(USER, self.REQUEST)

        assert outcome.done == []
        assert outcome.failed[0].status == TASK_LEFT_BEHIND

    async def test_a_list_is_no_move_to_itself(self) -> None:
        with pytest.raises(ValidationError):
            TaskSelectionMove(list_id="l1", task_ids=["t1"], destination_list_id="l1")


class TestClearingWhatIsDone:
    def _client(self, *pages: dict[str, Any]) -> MagicMock:
        client = _client(delete_task=True)
        client.list_tasks = AsyncMock(side_effect=list(pages))
        return client

    async def test_every_completed_task_is_deleted_and_no_other(self) -> None:
        client = self._client(
            {
                "items": [
                    {"id": "t1", "status": "completed"},
                    {"id": "t2", "status": "needsAction"},
                ],
                "next_page_token": None,
            }
        )

        with _door(client):
            cleared = await tasks_organize.clear_completed(USER, "l1")

        assert [call.args for call in client.delete_task.await_args_list] == [("l1", "t1")]
        assert cleared.deleted == 1
        assert cleared.remaining is False

    async def test_it_reads_what_google_hides(self) -> None:
        client = self._client({"items": [], "next_page_token": None})

        with _door(client):
            await tasks_organize.clear_completed(USER, "l1")

        kwargs = client.list_tasks.await_args.kwargs
        assert kwargs["show_completed"] is True and kwargs["show_hidden"] is True

    async def test_it_walks_the_pages(self) -> None:
        client = self._client(
            {"items": [{"id": "t1", "status": "completed"}], "next_page_token": "p2"},
            {"items": [{"id": "t2", "status": "completed"}], "next_page_token": None},
        )

        with _door(client):
            cleared = await tasks_organize.clear_completed(USER, "l1")

        assert cleared.deleted == 2

    async def test_past_the_bound_it_stops_and_says_more_remain(self) -> None:
        many = [
            {"id": f"t{index}", "status": "completed"}
            for index in range(WORKBENCH_TASKS_CLEAR_MAX + 1)
        ]
        client = self._client({"items": many, "next_page_token": None})

        with _door(client):
            cleared = await tasks_organize.clear_completed(USER, "l1")

        assert cleared.deleted == WORKBENCH_TASKS_CLEAR_MAX
        assert cleared.remaining is True

    async def test_a_subtask_gone_with_its_parent_is_no_failure(self) -> None:
        client = self._client(
            {
                "items": [
                    {"id": "t1", "status": "completed"},
                    {"id": "t2", "status": "completed", "parent": "t1"},
                ],
                "next_page_token": None,
            }
        )
        client.delete_task = AsyncMock(side_effect=[True, _gone()])

        with _door(client):
            cleared = await tasks_organize.clear_completed(USER, "l1")

        assert cleared.deleted == 2
        assert cleared.remaining is False


class TestOrdering:
    async def test_a_task_follows_another(self) -> None:
        client = _client(place_task={"id": "t1", "position": "2"})

        with _door(client):
            placed = await tasks_organize.place_task(
                USER, PARIS, TaskPlacement(list_id="l1", task_id="t1", after="t0")
            )

        client.place_task.assert_awaited_once_with("l1", "t1", "t0")
        assert placed.position == "2"

    async def test_to_do_keeps_no_order(self) -> None:
        client = _client(place_task={})

        with _door(client, TODO), pytest.raises(BaseAPIException) as refused:
            await tasks_organize.place_task(
                USER, PARIS, TaskPlacement(list_id="l1", task_id="t1", after=None)
            )

        assert refused.value.detail["code"] == NOT_SUPPORTED_BY_PROVIDER
        client.place_task.assert_not_awaited()


class TestSteps:
    async def test_one_is_added_once_per_submission(self) -> None:
        client = _client(add_task_step={"id": "s1", "title": "Next", "checked": False})
        request = NewTaskStep(list_id="l1", task_id="t1", title="Next", idempotency_key=KEY)

        with _door(client, TODO):
            step = await tasks_organize.add_step(USER, request)
            with pytest.raises(BaseAPIException):
                await tasks_organize.add_step(USER, request)

        client.add_task_step.assert_awaited_once_with("l1", "t1", "Next")
        assert step.id == "s1"

    async def test_one_is_ticked(self) -> None:
        client = _client(change_task_step={"id": "s1", "title": "Next", "checked": True})

        with _door(client, TODO):
            step = await tasks_organize.change_step(
                USER, TaskStepChange(list_id="l1", task_id="t1", step_id="s1", checked=True)
            )

        client.change_task_step.assert_awaited_once_with("l1", "t1", "s1", title=None, checked=True)
        assert step.checked is True

    async def test_one_is_removed(self) -> None:
        client = _client(remove_task_step=None)

        with _door(client, TODO):
            await tasks_organize.remove_step(USER, list_id="l1", task_id="t1", step_id="s1")

        client.remove_task_step.assert_awaited_once_with("l1", "t1", "s1")

    def test_a_change_names_something(self) -> None:
        with pytest.raises(ValidationError):
            TaskStepChange(list_id="l1", task_id="t1", step_id="s1")

    async def test_google_holds_none(self) -> None:
        client = _client(add_task_step={})
        request = NewTaskStep(list_id="l1", task_id="t1", title="Next", idempotency_key=KEY)

        with _door(client, GOOGLE), pytest.raises(BaseAPIException) as refused:
            await tasks_organize.add_step(USER, request)

        assert refused.value.detail["code"] == NOT_SUPPORTED_BY_PROVIDER


class TestDetails:
    REMINDER = datetime(2027, 1, 10, 9, 0, tzinfo=UTC)

    async def test_a_new_task_carries_them_and_its_steps(self) -> None:
        client = _client(create_task={"id": "t1", "title": "New", "importance": "high"})

        with _door(client, TODO):
            created = await tasks_service.create_task(
                USER,
                PARIS,
                NewTask(
                    list_id="l1",
                    title="New",
                    due=date(2027, 1, 11),
                    importance="high",
                    reminder=self.REMINDER,
                    repeat="weekly",
                    steps=["One"],
                    idempotency_key=KEY,
                ),
            )

        kwargs = client.create_task.await_args.kwargs
        assert kwargs["details"] == TaskDetails(
            importance="high",
            reminder=self.REMINDER,
            repeat="weekly",
            repeat_from=date(2027, 1, 11),
        )
        assert kwargs["steps"] == ("One",)
        assert created.importance == "high"

    async def test_nothing_of_the_kind_sends_none(self) -> None:
        client = _client(create_task={"id": "t1", "title": "New"})

        with _door(client, GOOGLE):
            await tasks_service.create_task(
                USER, PARIS, NewTask(list_id="l1", title="New", idempotency_key=KEY)
            )

        assert client.create_task.await_args.kwargs["details"] is None
        assert client.create_task.await_args.kwargs["steps"] == ()

    @pytest.mark.parametrize(
        "extra",
        [{"importance": "high"}, {"reminder": REMINDER}, {"steps": ["One"]}],
    )
    async def test_google_is_refused_them_unsent(self, extra: dict[str, Any]) -> None:
        client = _client(create_task={})

        with _door(client, GOOGLE), pytest.raises(BaseAPIException) as refused:
            await tasks_service.create_task(
                USER, PARIS, NewTask(list_id="l1", title="New", idempotency_key=KEY, **extra)
            )

        assert refused.value.detail["code"] == NOT_SUPPORTED_BY_PROVIDER
        client.create_task.assert_not_awaited()

    def test_a_new_repetition_needs_a_day(self) -> None:
        with pytest.raises(ValidationError):
            NewTask(list_id="l1", title="New", repeat="daily", idempotency_key=KEY)

    async def test_a_change_repeats_from_the_day_it_sends(self) -> None:
        client = _client(update_task={"id": "t1"})

        with _door(client, TODO):
            await tasks_service.update_task(
                USER,
                PARIS,
                TaskChange(list_id="l1", task_id="t1", due=date(2027, 2, 1), repeat="monthly"),
            )

        details = client.update_task.await_args.kwargs["details"]
        assert details.repeat_from == date(2027, 2, 1)
        client.get_task.assert_not_called()

    async def test_a_change_repeats_from_the_day_the_task_holds(self) -> None:
        client = _client(
            update_task={"id": "t1"}, get_task={"id": "t1", "due": "2027-03-04T23:00:00.000Z"}
        )

        with _door(client, TODO):
            await tasks_service.update_task(
                USER, PARIS, TaskChange(list_id="l1", task_id="t1", repeat="monthly")
            )

        assert client.update_task.await_args.kwargs["details"].repeat_from == date(2027, 3, 5)

    async def test_a_repetition_of_a_task_with_no_day_is_refused(self) -> None:
        client = _client(update_task={}, get_task={"id": "t1"})

        with _door(client, TODO), pytest.raises(BaseAPIException) as refused:
            await tasks_service.update_task(
                USER, PARIS, TaskChange(list_id="l1", task_id="t1", repeat="monthly")
            )

        assert refused.value.detail["code"] == INVALID_REQUEST
        client.update_task.assert_not_awaited()

    async def test_a_null_takes_a_reminder_and_a_repetition_off(self) -> None:
        client = _client(update_task={"id": "t1"})

        with _door(client, TODO):
            await tasks_service.update_task(
                USER,
                PARIS,
                TaskChange(list_id="l1", task_id="t1", reminder=None, repeat=None),
            )

        details = client.update_task.await_args.kwargs["details"]
        assert details.clear_reminder is True and details.clear_repeat is True

    async def test_a_plain_change_sends_no_details(self) -> None:
        client = _client(update_task={"id": "t1"})

        with _door(client, GOOGLE):
            await tasks_service.update_task(
                USER, PARIS, TaskChange(list_id="l1", task_id="t1", title="New")
            )

        assert client.update_task.await_args.kwargs["details"] is None

    async def test_what_is_read_reaches_the_screen(self) -> None:
        raw = {
            "id": "t1",
            "importance": "high",
            "reminder": "2027-01-10T09:00:00.000Z",
            "repeat": "weekly",
            "steps": [{"id": "s1", "title": "One", "checked": True}],
        }
        client = _client(list_tasks={"items": [raw], "next_page_token": None})

        with _door(client, TODO):
            page = await tasks_service.list_tasks(USER, PARIS, list_id="l1")

        task = page.items[0]
        assert task.importance == "high"
        assert task.reminder == self.REMINDER
        assert task.repeat == "weekly"
        assert task.steps[0].checked is True

    async def test_google_reads_none_of_it(self) -> None:
        client = _client(list_tasks={"items": [{"id": "t1"}], "next_page_token": None})

        with _door(client, GOOGLE):
            page = await tasks_service.list_tasks(USER, PARIS, list_id="l1")

        task = page.items[0]
        assert task.importance is None and task.reminder is None and task.repeat is None
        assert task.steps == []
