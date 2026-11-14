"""What the assistant reads of a person's tasks: every list, or the one named (2026-11-10).

Every list is read unless the model names one; each task carries its own list; what was not
read is said, and « no task » is never told on a list nobody could read (ADR-185, ADR-303).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.core.constants import TASK_LISTS_READ_MAX
from src.core.exceptions import ExternalServiceError
from src.core.field_names import FIELD_TASK_LIST_ID, FIELD_TASK_LIST_NAME
from src.domains.agents.tools.exceptions import ToolValidationError
from src.domains.agents.tools.tasks_reading import TasksRead, partial_read_note, read_tasks
from src.domains.connectors.clients.task_lists import PROVIDER_FAILURES, TaskListing

pytestmark = pytest.mark.unit

_LISTING = TaskListing(max_results=10)
_DOWN = httpx.ConnectError("down")


def _client(pages: dict[str, Any], *, more_lists: bool = False) -> MagicMock:
    """An account whose lists (``l1`` is « L1 ») answer a page or fail."""

    async def read(list_id: str, **_kwargs: Any) -> dict[str, Any]:
        answer = pages[list_id]
        if isinstance(answer, Exception):
            raise answer
        return dict(answer)

    listed = {
        "items": [{"id": list_id, "title": list_id.upper()} for list_id in pages],
        "next_page_token": "next" if more_lists else None,
    }
    return MagicMock(
        list_tasks=AsyncMock(side_effect=read), list_task_lists=AsyncMock(return_value=listed)
    )


def _page(*task_ids: str, more: bool = False) -> dict[str, Any]:
    return {
        "items": [{"id": task_id} for task_id in task_ids],
        "next_page_token": "next" if more else None,
    }


def _ids(read: TasksRead) -> list[str]:
    return [task["id"] for task in read.tasks]


class TestEveryList:
    @pytest.mark.parametrize("given", [None, "", "@default"])
    async def test_every_list_is_read_when_none_is_named(self, given: str | None) -> None:
        client = _client({"l1": _page("a", "b"), "l2": _page("c")})

        read = await read_tasks(client, given, _LISTING)

        assert _ids(read) == ["a", "b", "c"]
        assert read.list_id is None
        assert (read.more_exist, read.unread_lists) == (False, [])
        client.list_task_lists.assert_awaited_once_with(TASK_LISTS_READ_MAX)

    async def test_each_task_carries_its_own_list(self) -> None:
        read = await read_tasks(_client({"l1": _page("a"), "l2": _page("c")}), None, _LISTING)

        assert [(task[FIELD_TASK_LIST_ID], task[FIELD_TASK_LIST_NAME]) for task in read.tasks] == [
            ("l1", "L1"),
            ("l2", "L2"),
        ]

    async def test_a_list_that_fails_is_named_and_the_others_answer(self) -> None:
        client = _client({"l1": _page("a"), "l2": _DOWN, "l3": _page("c")})

        read = await read_tasks(client, None, _LISTING)

        assert _ids(read) == ["a", "c"]
        assert read.unread_lists == ["L2"]

    async def test_no_task_is_never_told_on_a_list_nobody_read(self) -> None:
        """Nothing beside a failed list is that failure, not an empty day."""
        client = _client({"l1": _page(), "l2": _DOWN})

        with pytest.raises(httpx.ConnectError):
            await read_tasks(client, None, _LISTING)

    async def test_every_list_failing_is_the_first_failure(self) -> None:
        refused = ExternalServiceError(service_name="tasks", detail="refused")

        with pytest.raises(ExternalServiceError):
            await read_tasks(_client({"l1": refused, "l2": _DOWN}), None, _LISTING)

    @pytest.mark.parametrize("pages", [{}, {"l1": _page(), "l2": _page()}])
    async def test_an_account_with_nothing_to_do_is_an_empty_read(
        self, pages: dict[str, Any]
    ) -> None:
        read = await read_tasks(_client(pages), None, _LISTING)

        assert read == TasksRead(tasks=[])

    async def test_a_list_holding_more_than_was_read_says_so(self) -> None:
        read = await read_tasks(
            _client({"l1": _page("a", more=True), "l2": _page("c")}), None, _LISTING
        )

        assert read.more_exist is True

    async def test_more_lists_than_were_read_says_so(self) -> None:
        read = await read_tasks(_client({"l1": _page("a")}, more_lists=True), None, _LISTING)

        assert read.more_exist is True

    async def test_a_failure_nobody_declared_is_not_swallowed(self) -> None:
        assert not issubclass(KeyError, PROVIDER_FAILURES)

        with pytest.raises(KeyError):
            await read_tasks(_client({"l1": _page("a"), "l2": KeyError("bug")}), None, _LISTING)


class TestTheListNamed:
    @pytest.mark.parametrize("given", ["l2", "L2", "l2 "])
    async def test_it_is_read_alone_by_its_id_or_its_name(self, given: str) -> None:
        client = _client({"l1": _page("a"), "l2": _page("c", "b")})

        read = await read_tasks(client, given, _LISTING)

        assert _ids(read) == ["c", "b"], "the provider's own order, the person's"
        assert read.list_id == "l2"
        assert [call.args[0] for call in client.list_tasks.await_args_list] == ["l2"]
        assert {(task[FIELD_TASK_LIST_ID], task[FIELD_TASK_LIST_NAME]) for task in read.tasks} == {
            ("l2", "L2")
        }

    async def test_holding_more_than_was_read_it_says_so(self) -> None:
        read = await read_tasks(_client({"l1": _page("a", more=True)}), "l1", _LISTING)

        assert read.more_exist is True

    async def test_its_failure_is_the_read_s(self) -> None:
        """One list asked, one list down: there is no other answer to give."""
        with pytest.raises(httpx.ConnectError):
            await read_tasks(_client({"l1": _DOWN, "l2": _page("c")}), "l1", _LISTING)

    async def test_a_list_nobody_has_reads_nothing(self) -> None:
        client = _client({"l1": _page("a")})

        with pytest.raises(ToolValidationError):
            await read_tasks(client, "Work", _LISTING)

        client.list_tasks.assert_not_awaited()

    async def test_what_is_asked_of_a_list_reaches_the_provider(self) -> None:
        client = _client({"l1": _page("a")})
        listing = TaskListing(
            max_results=7,
            show_completed=True,
            show_hidden=True,
            due_min="2026-11-10T00:00:00Z",
            due_max="2026-11-17T00:00:00Z",
        )

        await read_tasks(client, "l1", listing)

        asked = client.list_tasks.await_args.kwargs
        assert (asked["max_results"], asked["show_completed"], asked["show_hidden"]) == (
            7,
            True,
            True,
        )
        assert (asked["due_min"], asked["due_max"]) == (listing.due_min, listing.due_max)


class TestWhatAnAnswerShows:
    """One order across lists, the answer's bound, and whether it left some out."""

    _SOON, _LATER = "2026-11-12T00:00:00.000Z", "2026-11-20T00:00:00.000Z"

    def _tasks(self) -> list[dict[str, Any]]:
        return [
            {"id": "later", "due": self._LATER},
            {"id": "undated"},
            {"id": "soon", "due": self._SOON, "status": "completed"},
        ]

    def test_several_lists_stand_in_due_order(self) -> None:
        shown, more = TasksRead(tasks=self._tasks()).shown(10, timezone="UTC")

        assert [task["id"] for task in shown] == ["soon", "later", "undated"]
        assert more is False

    def test_a_list_read_alone_keeps_its_own_order(self) -> None:
        shown, _more = TasksRead(tasks=self._tasks(), list_id="l1").shown(10, timezone="UTC")

        assert [task["id"] for task in shown] == ["later", "undated", "soon"]

    def test_the_answer_s_bound_cuts_after_the_order_and_says_so(self) -> None:
        shown, more = TasksRead(tasks=self._tasks()).shown(2, timezone="UTC")

        assert [task["id"] for task in shown] == ["soon", "later"]
        assert more is True

    def test_a_read_already_cut_stays_said_whatever_the_bound(self) -> None:
        _shown, more = TasksRead(tasks=self._tasks(), more_exist=True).shown(10, timezone="UTC")

        assert more is True

    def test_only_what_is_done_is_kept_when_asked(self) -> None:
        shown, more = TasksRead(tasks=self._tasks()).shown(10, timezone="UTC", only_completed=True)

        assert [task["id"] for task in shown] == ["soon"]
        assert more is False


class TestWhatWasNotRead:
    def test_nothing_is_said_when_everything_was_read(self) -> None:
        assert partial_read_note(more_exist=False, unread_lists=[]) == ""

    def test_a_cut_is_stated(self) -> None:
        note = partial_read_note(more_exist=True, unread_lists=[])

        assert note.startswith("More tasks exist than are returned here")

    def test_each_list_that_could_not_be_read_is_named(self) -> None:
        note = partial_read_note(more_exist=False, unread_lists=["Home", "Bills"])

        assert "Home, Bills" in note and "could not be read" in note

    def test_both_are_said_together(self) -> None:
        note = partial_read_note(more_exist=True, unread_lists=["Home"])

        assert "More tasks exist" in note and "Home" in note
