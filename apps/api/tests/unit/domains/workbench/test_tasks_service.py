"""The tasks of the « Tools » section, by hand (ADR-369, Task 6.1).

What the screen is told: a page cut at its ceiling says more exists (review
focus 1); a due date is a DAY — Google keeps a date, To Do keeps the instant of
local midnight, read and written in the account's zone, a DST night included;
completion is a boolean; a removed due date is removed, an absent one kept; a
gesture the provider lacks is refused before anything is sent; a create runs
once per submission, whatever is clicked twice.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from src.core.config import settings
from src.core.exceptions import BaseAPIException, ConnectorAPIError
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.preferences.owner_defaults import TASK_LIST
from src.domains.workbench import idempotency, tasks_service
from src.domains.workbench.schemas.tasks import NewTask, NewTaskList, TaskChange
from tests.unit.domains.workbench.fakes import FakeRedis

pytestmark = pytest.mark.unit

USER = uuid4()
PARIS = ZoneInfo("Europe/Paris")
NEW_YORK = ZoneInfo("America/New_York")
GOOGLE, MICROSOFT = ConnectorType.GOOGLE_TASKS, ConnectorType.MICROSOFT_TASKS


@pytest.fixture(autouse=True)
def _redis() -> Any:
    """Every create claims its key in a Redis of the test's own: no real one is reached."""
    with patch.object(idempotency, "get_redis_cache", AsyncMock(return_value=FakeRedis())):
        yield


def _door(client: Any, kind: ConnectorType = GOOGLE, preferred: str | None = None) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any, container: Any = None) -> AsyncIterator[ActiveClient]:
        assert user_id == USER
        # Only the task list's own preference is ever read for the lists.
        name = preferred if container is TASK_LIST else None
        yield ActiveClient(client=client, connector_type=kind, preferred_name=name)

    return patch.object(tasks_service, "open_tool_client", opened)


def _client(**methods: Any) -> MagicMock:
    return MagicMock(**{name: AsyncMock(return_value=value) for name, value in methods.items()})


def _page_size() -> int:
    return min(settings.workbench_page_size, settings.api_max_items_per_request)


class TestPages:
    async def test_a_page_cut_at_its_ceiling_says_more_exists(self) -> None:
        full = [{"id": f"t{index}", "title": "x"} for index in range(_page_size())]
        client = _client(list_tasks={"items": full, "next_page_token": "p2"})
        with _door(client):
            page = await tasks_service.list_tasks(USER, PARIS, list_id="l1")

        assert (len(page.items), page.next_page_token) == (_page_size(), "p2")
        assert client.list_tasks.await_args.kwargs["max_results"] == _page_size()

    async def test_the_next_page_is_asked_with_its_token(self) -> None:
        client = _client(list_tasks={"items": [], "next_page_token": None})
        with _door(client):
            page = await tasks_service.list_tasks(USER, PARIS, list_id="l1", page_token="p2")

        assert client.list_tasks.await_args.kwargs["page_token"] == "p2"
        assert page.next_page_token is None

    async def test_completed_tasks_are_asked_hidden_ones_too(self) -> None:
        """Google hides a task completed in its own apps unless asked for hidden ones."""
        client = _client(list_tasks={"items": []})
        with _door(client):
            await tasks_service.list_tasks(USER, PARIS, list_id="l1", show_completed=True)

        kwargs = client.list_tasks.await_args.kwargs
        assert (kwargs["show_completed"], kwargs["show_hidden"]) == (True, True)

    async def test_the_lists_page_too(self) -> None:
        client = _client(
            list_task_lists={"items": [{"id": "l1", "title": "Home"}], "next_page_token": "p2"}
        )
        with _door(client):
            page = await tasks_service.list_task_lists(USER)

        assert [(item.id, item.title) for item in page.items] == [("l1", "Home")]
        assert page.next_page_token == "p2"


class TestADueDateIsADay:
    async def test_google_keeps_the_day_whatever_the_zone(self) -> None:
        stored = {"id": "t1", "title": "Pay", "due": "2026-11-03T00:00:00.000Z"}
        client = _client(create_task=stored, list_tasks={"items": [stored]})
        with _door(client):
            created = await tasks_service.create_task(
                USER, NEW_YORK, NewTask(list_id="l1", title="Pay", due=date(2026, 11, 3), **_key())
            )
            listed = await tasks_service.list_tasks(USER, NEW_YORK, list_id="l1")

        assert client.create_task.await_args.kwargs["due"] == "2026-11-03T00:00:00.000Z"
        assert created.due == listed.items[0].due == date(2026, 11, 3)

    @pytest.mark.parametrize(
        ("day", "instant"),
        [
            (date(2026, 11, 3), "2026-11-02T23:00:00"),
            # The night Paris moves to summer time: midnight is still UTC+1.
            (date(2026, 3, 29), "2026-03-28T23:00:00"),
            (date(2026, 3, 30), "2026-03-29T22:00:00"),
        ],
    )
    async def test_to_do_keeps_local_midnight(self, day: date, instant: str) -> None:
        stored = {"id": "t1", "title": "Pay", "due": f"{instant}.000Z"}
        client = _client(create_task=stored)
        with _door(client, MICROSOFT):
            created = await tasks_service.create_task(
                USER, PARIS, NewTask(list_id="l1", title="Pay", due=day, **_key())
            )

        assert client.create_task.await_args.kwargs["due"] == instant
        assert created.due == day

    async def test_a_task_without_a_date_has_none(self) -> None:
        client = _client(list_tasks={"items": [{"id": "t1", "title": "x", "due": None}]})
        with _door(client, MICROSOFT):
            page = await tasks_service.list_tasks(USER, PARIS, list_id="l1")
        assert page.items[0].due is None


class TestChanges:
    async def test_completing_and_reopening(self) -> None:
        client = _client(update_task={"id": "t1", "title": "x", "status": "completed"})
        with _door(client):
            done = await tasks_service.update_task(
                USER, PARIS, TaskChange(list_id="l1", task_id="t1", completed=True)
            )
            await tasks_service.update_task(
                USER, PARIS, TaskChange(list_id="l1", task_id="t1", completed=False)
            )

        statuses = [call.kwargs["status"] for call in client.update_task.await_args_list]
        assert statuses == ["completed", "needsAction"]
        assert done.completed is True

    async def test_a_null_due_removes_it_and_an_absent_one_keeps_it(self) -> None:
        client = _client(update_task={"id": "t1", "title": "x"})
        with _door(client):
            await tasks_service.update_task(
                USER, PARIS, TaskChange(list_id="l1", task_id="t1", due=None)
            )
            await tasks_service.update_task(
                USER, PARIS, TaskChange(list_id="l1", task_id="t1", title="y")
            )

        removed, kept = (call.kwargs for call in client.update_task.await_args_list)
        assert (removed["clear_due"], removed["due"]) == (True, None)
        assert (kept["clear_due"], kept["due"]) == (False, None)

    def test_a_change_that_changes_nothing_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            TaskChange(list_id="l1", task_id="t1")

    async def test_a_gone_task_reads_item_gone(self) -> None:
        client = MagicMock(
            update_task=AsyncMock(
                side_effect=ConnectorAPIError(
                    connector_type="google_tasks", status_code=404, detail="x"
                )
            )
        )
        with _door(client), pytest.raises(BaseAPIException) as refused:
            await tasks_service.update_task(
                USER, PARIS, TaskChange(list_id="l1", task_id="t1", title="y")
            )
        assert refused.value.detail == {"code": "item_gone"}


class TestWhatAProviderLacks:
    async def test_a_subtask_on_to_do_is_refused_unsent(self) -> None:
        client = _client(create_task={"id": "t2"})
        with _door(client, MICROSOFT), pytest.raises(BaseAPIException) as refused:
            await tasks_service.create_task(
                USER, PARIS, NewTask(list_id="l1", title="Sub", parent="t1", **_key())
            )
        assert refused.value.detail == {"code": "not_supported_by_provider"}
        client.create_task.assert_not_awaited()

    async def test_a_subtask_on_google_names_its_parent(self) -> None:
        client = _client(create_task={"id": "t2", "title": "Sub", "parent": "t1"})
        with _door(client):
            created = await tasks_service.create_task(
                USER, PARIS, NewTask(list_id="l1", title="Sub", parent="t1", **_key())
            )
        assert client.create_task.await_args.kwargs["parent"] == "t1"
        assert created.parent == "t1"


class TestOncePerSubmission:
    async def test_a_second_click_creates_nothing_and_names_the_first(self) -> None:
        client = _client(create_task={"id": "t9", "title": "Pay"})
        request = NewTask(list_id="l1", title="Pay", **_key())
        with _door(client):
            await tasks_service.create_task(USER, PARIS, request)
            with pytest.raises(BaseAPIException) as replayed:
                await tasks_service.create_task(USER, PARIS, request)

        assert replayed.value.status_code == 409
        assert replayed.value.detail == {
            "code": "already_submitted",
            "outcome": "done",
            "task_id": "t9",
        }
        client.create_task.assert_awaited_once()

    async def test_a_list_too(self) -> None:
        client = _client(create_task_list={"id": "l9", "title": "Trip"})
        request = NewTaskList(title="Trip", **_key())
        with _door(client):
            created = await tasks_service.create_task_list(USER, request)
            with pytest.raises(BaseAPIException):
                await tasks_service.create_task_list(USER, request)

        assert (created.id, created.title) == ("l9", "Trip")
        client.create_task_list.assert_awaited_once()


def _key() -> dict[str, Any]:
    return {"idempotency_key": uuid4()}


class TestTheDefaultList:
    """The default the person chose in the settings is the list the page opens on."""

    LISTS = {
        "items": [{"id": "a", "title": "Mes tâches"}, {"id": "b", "title": "Maison"}],
        "next_page_token": None,
    }

    async def test_the_chosen_list_is_named_whatever_its_case(self) -> None:
        client = MagicMock(list_task_lists=AsyncMock(return_value=self.LISTS))
        with _door(client, preferred="MAISON"):
            page = await tasks_service.list_task_lists(USER)

        assert [item.id for item in page.items if item.default] == ["b"]

    async def test_nothing_is_the_default_when_nothing_was_chosen(self) -> None:
        client = MagicMock(list_task_lists=AsyncMock(return_value=self.LISTS))
        with _door(client):
            page = await tasks_service.list_task_lists(USER)

        assert not any(item.default for item in page.items)
