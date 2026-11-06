"""Organising tasks on Google Tasks and Microsoft To Do (ADR-369, lot 9).

Measured on a real To Do on 2026-11-05. A list renames in place. A move is Google's own act and
none of To Do's: `/move` answers 400, and a PATCH of `parentListId` answers 200 and moves
nothing, so a task is copied, then its original removed: never lost, and said when it could not
be removed. To Do alone keeps steps, an importance, a reminder and a repetition: Google is
refused rather than left to drop them. Google alone keeps an order.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.clients.google_tasks_client import GoogleTasksClient
from src.domains.connectors.clients.microsoft_tasks_client import MicrosoftTasksClient
from src.domains.connectors.clients.normalizers.microsoft_tasks_normalizer import (
    normalize_graph_task,
)
from src.domains.connectors.clients.task_details import (
    REPEAT_CUSTOM,
    TaskDetails,
    TaskLeftBehindError,
    graph_recurrence,
    repeat_of,
)
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit


def _credentials() -> ConnectorCredentials:
    return ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


def _google(*answers: Any) -> tuple[GoogleTasksClient, AsyncMock]:
    client = GoogleTasksClient(uuid4(), _credentials(), MagicMock())
    request = AsyncMock(side_effect=list(answers))
    client._make_request = request
    return client, request


def _todo(*answers: Any) -> tuple[MicrosoftTasksClient, AsyncMock]:
    client = MicrosoftTasksClient(uuid4(), _credentials(), MagicMock())
    request = AsyncMock(side_effect=list(answers))
    client._make_request = request
    return client, request


def _refused(status: int) -> ConnectorAPIError:
    return ConnectorAPIError(connector_type="microsoft_tasks", status_code=status, detail="x")


READ_TASK: dict[str, Any] = {
    "id": "t1",
    "title": "Proof",
    "status": "notStarted",
    "importance": "high",
    "categories": ["Blue"],
    "body": {"content": "Words", "contentType": "text"},
    "isReminderOn": False,
    "createdDateTime": "2026-11-05T09:00:00Z",
    "lastModifiedDateTime": "2026-11-05T09:00:00Z",
    "hasAttachments": False,
    "@odata.etag": 'W/"x"',
    "checklistItems": [
        {"id": "s1", "displayName": "Step", "isChecked": True, "createdDateTime": "x"},
    ],
}


class TestRenamingAList:
    async def test_google(self) -> None:
        client, request = _google({"id": "l1", "title": "New"})

        renamed = await client.rename_task_list("l1", "New")

        assert request.await_args.args[:2] == ("PATCH", "/users/@me/lists/l1")
        assert request.await_args.kwargs["json_data"] == {"title": "New"}
        assert renamed["title"] == "New"

    async def test_to_do(self) -> None:
        client, request = _todo({"id": "l1", "displayName": "New"})

        renamed = await client.rename_task_list("l1", "New")

        assert request.await_args.args[:2] == ("PATCH", "/me/todo/lists/l1")
        assert request.await_args.kwargs["json_data"] == {"displayName": "New"}
        assert renamed["title"] == "New"


class TestMovingATask:
    async def test_google_moves_it_by_name(self) -> None:
        client, request = _google({"id": "t1", "title": "Proof"})

        moved = await client.move_task("l1", "t1", "l2")

        assert request.await_args.args[:2] == ("POST", "/lists/l1/tasks/t1/move")
        assert request.await_args.kwargs["params"] == {"destinationTasklist": "l2"}
        assert moved["id"] == "t1"

    async def test_to_do_copies_what_it_holds_then_removes_the_original(self) -> None:
        client, request = _todo(READ_TASK, {"id": "t2", "title": "Proof"}, {})

        moved = await client.move_task("l1", "t1", "l2")

        read, copy, removal = request.await_args_list
        assert read.args[:2] == ("GET", "/me/todo/lists/l1/tasks/t1")
        assert copy.args[:2] == ("POST", "/me/todo/lists/l2/tasks")
        body = copy.kwargs["json_data"]
        assert body["title"] == "Proof"
        assert body["importance"] == "high"
        assert body["categories"] == ["Blue"]
        assert body["checklistItems"] == [{"displayName": "Step", "isChecked": True}]
        assert "createdDateTime" not in body and "@odata.etag" not in body and "id" not in body
        assert removal.args[:2] == ("DELETE", "/me/todo/lists/l1/tasks/t1")
        assert moved["id"] == "t2"

    async def test_to_do_removes_nothing_when_the_copy_failed(self) -> None:
        client, request = _todo(READ_TASK, _refused(403))

        with pytest.raises(ConnectorAPIError):
            await client.move_task("l1", "t1", "l2")

        assert [call.args[0] for call in request.await_args_list] == ["GET", "POST"]

    async def test_to_do_says_a_task_left_in_both(self) -> None:
        client, _request = _todo(READ_TASK, {"id": "t2", "title": "Proof"}, _refused(500))

        with pytest.raises(TaskLeftBehindError):
            await client.move_task("l1", "t1", "l2")


class TestOrdering:
    async def test_google_places_a_task_after_another(self) -> None:
        client, request = _google({"id": "t1"})

        await client.place_task("l1", "t1", "t0")

        assert request.await_args.args[:2] == ("POST", "/lists/l1/tasks/t1/move")
        assert request.await_args.kwargs["params"] == {"previous": "t0"}

    async def test_nothing_before_it_puts_it_first(self) -> None:
        client, request = _google({"id": "t1"})

        await client.place_task("l1", "t1", None)

        assert not request.await_args.kwargs.get("params")


class TestSteps:
    async def test_tasks_are_read_with_their_steps(self) -> None:
        client, request = _todo({"value": [READ_TASK]})

        page = await client.list_tasks("l1")

        assert request.await_args.args[2]["$expand"] == "checklistItems"
        assert page["items"][0]["steps"] == [{"id": "s1", "title": "Step", "checked": True}]

    async def test_a_task_is_read_with_its_steps(self) -> None:
        client, request = _todo(READ_TASK)

        task = await client.get_task("l1", "t1")

        assert request.await_args.args[2] == {"$expand": "checklistItems"}
        assert task["steps"][0]["checked"] is True

    async def test_a_step_is_added(self) -> None:
        client, request = _todo({"id": "s2", "displayName": "Next", "isChecked": False})

        step = await client.add_task_step("l1", "t1", "Next")

        assert request.await_args.args[:2] == (
            "POST",
            "/me/todo/lists/l1/tasks/t1/checklistItems",
        )
        assert request.await_args.kwargs["json_data"] == {"displayName": "Next"}
        assert step == {"id": "s2", "title": "Next", "checked": False}

    async def test_a_step_is_ticked_and_renamed_by_what_is_sent(self) -> None:
        client, request = _todo({"id": "s1", "displayName": "Step", "isChecked": True})

        await client.change_task_step("l1", "t1", "s1", checked=True)

        assert request.await_args.args[:2] == (
            "PATCH",
            "/me/todo/lists/l1/tasks/t1/checklistItems/s1",
        )
        assert request.await_args.kwargs["json_data"] == {"isChecked": True}

    async def test_a_step_is_removed(self) -> None:
        client, request = _todo({})

        await client.remove_task_step("l1", "t1", "s1")

        assert request.await_args.args[:2] == (
            "DELETE",
            "/me/todo/lists/l1/tasks/t1/checklistItems/s1",
        )

    async def test_a_new_task_carries_its_steps(self) -> None:
        client, request = _todo({"id": "t1", "title": "New"})

        await client.create_task("l1", "New", steps=("One", "Two"))

        assert request.await_args.kwargs["json_data"]["checklistItems"] == [
            {"displayName": "One"},
            {"displayName": "Two"},
        ]


class TestDetails:
    async def test_a_new_task_carries_what_to_do_keeps(self) -> None:
        client, request = _todo({"id": "t1", "title": "New"})
        reminder = datetime(2027, 1, 10, 9, 0, tzinfo=UTC)

        await client.create_task(
            "l1",
            "New",
            details=TaskDetails(
                importance="high",
                reminder=reminder,
                repeat="weekly",
                repeat_from=date(2027, 1, 11),
            ),
        )

        body = request.await_args.kwargs["json_data"]
        assert body["importance"] == "high"
        assert body["isReminderOn"] is True
        assert body["reminderDateTime"] == {
            "dateTime": "2027-01-10T09:00:00.0000000",
            "timeZone": "UTC",
        }
        assert body["recurrence"]["pattern"] == {
            "type": "weekly",
            "interval": 1,
            "daysOfWeek": ["monday"],
        }

    async def test_a_reminder_keeps_its_instant_from_any_zone(self) -> None:
        client, request = _todo({"id": "t1", "title": "New"})
        paris = datetime(2027, 1, 10, 10, 0, tzinfo=UTC).astimezone()

        await client.update_task("l1", "t1", details=TaskDetails(reminder=paris))

        assert request.await_args.kwargs["json_data"]["reminderDateTime"]["dateTime"] == (
            "2027-01-10T10:00:00.0000000"
        )

    async def test_a_reminder_and_a_repetition_can_be_taken_off(self) -> None:
        client, request = _todo({"id": "t1", "title": "New"})

        await client.update_task(
            "l1", "t1", details=TaskDetails(clear_reminder=True, clear_repeat=True)
        )

        body = request.await_args.kwargs["json_data"]
        # Measured: `isReminderOn: false` alone answers 200 and leaves the reminder on.
        assert body == {"isReminderOn": False, "reminderDateTime": None, "recurrence": None}

    async def test_no_detail_touches_nothing(self) -> None:
        client, request = _todo({"id": "t1", "title": "New"})

        await client.update_task("l1", "t1", title="Renamed")

        assert request.await_args.kwargs["json_data"] == {"title": "Renamed"}

    @pytest.mark.parametrize(
        "kwargs",
        [{"details": TaskDetails(importance="high")}, {"steps": ("One",)}],
    )
    async def test_google_refuses_what_it_would_drop(self, kwargs: dict[str, Any]) -> None:
        client, request = _google()

        with pytest.raises(ValueError):
            await client.create_task("l1", "New", **kwargs)

        request.assert_not_awaited()

    async def test_google_refuses_a_detail_on_a_change(self) -> None:
        client, request = _google()

        with pytest.raises(ValueError):
            await client.update_task("l1", "t1", details=TaskDetails(importance="high"))

        request.assert_not_awaited()


class TestARepetition:
    @pytest.mark.parametrize(
        ("repeat", "pattern"),
        [
            ("daily", {"type": "daily", "interval": 1}),
            ("weekly", {"type": "weekly", "interval": 1, "daysOfWeek": ["wednesday"]}),
            ("monthly", {"type": "absoluteMonthly", "interval": 1, "dayOfMonth": 3}),
            ("yearly", {"type": "absoluteYearly", "interval": 1, "dayOfMonth": 3, "month": 2}),
        ],
    )
    def test_it_starts_on_its_day(self, repeat: str, pattern: dict[str, Any]) -> None:
        recurrence = graph_recurrence(repeat, date(2027, 2, 3))

        assert recurrence == {
            "pattern": pattern,
            "range": {"type": "noEnd", "startDate": "2027-02-03"},
        }

    @pytest.mark.parametrize("repeat", ["daily", "weekly", "monthly", "yearly"])
    def test_what_is_written_reads_back(self, repeat: str) -> None:
        assert repeat_of(graph_recurrence(repeat, date(2027, 2, 3))) == repeat

    def test_none_is_none(self) -> None:
        assert repeat_of(None) is None

    @pytest.mark.parametrize(
        "pattern",
        [
            {"type": "daily", "interval": 2},
            {"type": "weekly", "interval": 1, "daysOfWeek": ["monday", "friday"]},
            {"type": "relativeMonthly", "interval": 1, "daysOfWeek": ["monday"]},
        ],
    )
    def test_what_the_screen_cannot_say_stays_named_custom(self, pattern: dict[str, Any]) -> None:
        assert repeat_of({"pattern": pattern}) == REPEAT_CUSTOM


class TestWhatIsRead:
    def test_a_reminder_is_read_only_when_it_is_on(self) -> None:
        reminder = {"dateTime": "2027-01-10T09:00:00.0000000", "timeZone": "UTC"}

        off = normalize_graph_task({"id": "t", "isReminderOn": False, "reminderDateTime": reminder})
        on = normalize_graph_task({"id": "t", "isReminderOn": True, "reminderDateTime": reminder})

        assert off["reminder"] is None
        assert on["reminder"] == "2027-01-10T09:00:00.000Z"

    def test_a_task_with_no_step_has_none(self) -> None:
        assert normalize_graph_task({"id": "t"})["steps"] == []
