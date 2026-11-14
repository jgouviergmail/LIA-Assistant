"""Every task list read in one go: the walk every reader of a person's tasks shares.

A list that fails keeps its failure and the others answer; a list holding more than the pages
read says so (ADR-185); the lists are asked a few at a time, whoever reads; a failure the caller
did not name is not swallowed. Read together, each task carries its own list's real id and name.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.constants import TASK_LISTS_READ_CONCURRENCY
from src.core.field_names import FIELD_TASK_LIST_ID, FIELD_TASK_LIST_NAME
from src.domains.connectors.clients.task_lists import (
    PROVIDER_FAILURES,
    EveryTaskList,
    TaskListing,
    TaskListRead,
    read_every_task_list,
    read_task_lists,
)

pytestmark = pytest.mark.unit


class _Down(Exception):
    """A failure the caller lets a list fail on."""


def _client(pages: dict[str, Any], *, lists: dict[str, Any] | None = None) -> MagicMock:
    """A provider whose lists answer a page, an error or what a callable decides."""

    async def read(list_id: str, **kwargs: Any) -> dict[str, Any]:
        answer = pages[list_id]
        if isinstance(answer, Exception):
            raise answer
        result: dict[str, Any] = answer(kwargs) if callable(answer) else answer
        return result

    listed = lists or {
        "items": [{"id": list_id, "title": list_id.upper()} for list_id in pages],
        "next_page_token": None,
    }
    return MagicMock(
        list_tasks=AsyncMock(side_effect=read), list_task_lists=AsyncMock(return_value=listed)
    )


async def _walk(
    client: MagicMock, ids: list[str], listing: TaskListing | None = None, **options: Any
) -> list[TaskListRead]:
    asked = listing or TaskListing(max_results=10, pages_max=3)
    return await read_task_lists(client, ids, asked, **{"failures": (_Down,), **options})


class TestWhatEachListGives:
    async def test_one_read_per_list_in_the_order_given(self) -> None:
        client = _client({"a": {"items": [{"id": "t1"}]}, "b": {"items": [{"id": "t2"}]}})

        read = await _walk(client, ["b", "a"])

        assert [[task["id"] for task in item.items] for item in read] == [["t2"], ["t1"]]
        assert [(item.cut, item.failure) for item in read] == [(False, None), (False, None)]

    async def test_what_is_still_to_do_is_asked_unless_told_otherwise(self) -> None:
        client = _client({"a": {"items": []}})

        await _walk(client, ["a"], TaskListing(max_results=10, due_max="2026-11-17T00:00:00Z"))

        asked = client.list_tasks.await_args
        assert asked.args == ("a",)
        assert asked.kwargs == {
            "max_results": 10,
            "show_completed": False,
            "show_hidden": False,
            "due_min": None,
            "due_max": "2026-11-17T00:00:00Z",
            "completed_min": None,
            "page_token": None,
        }

    async def test_every_filter_asked_reaches_the_provider(self) -> None:
        client = _client({"a": {"items": []}})
        listing = TaskListing(
            max_results=7,
            show_completed=True,
            show_hidden=True,
            due_min="2026-11-11T00:00:00Z",
            completed_min="2026-11-10T00:00:00Z",
        )

        await _walk(client, ["a"], listing)

        asked = client.list_tasks.await_args.kwargs
        assert (asked["max_results"], asked["show_completed"], asked["show_hidden"]) == (
            7,
            True,
            True,
        )
        assert (asked["due_min"], asked["due_max"], asked["completed_min"]) == (
            "2026-11-11T00:00:00Z",
            None,
            "2026-11-10T00:00:00Z",
        )

    async def test_no_list_is_no_read(self) -> None:
        client = _client({})

        assert await _walk(client, []) == []
        client.list_tasks.assert_not_awaited()

    async def test_each_page_follows_the_token_of_the_one_before(self) -> None:
        def paged(kwargs: dict[str, Any]) -> dict[str, Any]:
            if kwargs["page_token"] is None:
                return {"items": [{"id": "first"}], "next_page_token": "p2"}
            return {"items": [{"id": "second"}], "next_page_token": None}

        client = _client({"a": paged})

        [read] = await _walk(client, ["a"])

        assert [task["id"] for task in read.items] == ["first", "second"]
        assert read.cut is False
        assert client.list_tasks.await_args.kwargs["page_token"] == "p2"

    async def test_one_page_is_read_unless_more_are_asked(self) -> None:
        def endless(kwargs: dict[str, Any]) -> dict[str, Any]:
            return {"items": [{"id": "t"}], "next_page_token": "more"}

        client = _client({"a": endless})

        [read] = await _walk(client, ["a"], TaskListing(max_results=10))

        assert client.list_tasks.await_count == 1
        assert read.cut is True


class TestWhatIsSaid:
    async def test_a_list_longer_than_the_pages_read_says_so(self) -> None:
        def endless(kwargs: dict[str, Any]) -> dict[str, Any]:
            return {"items": [{"id": "t"}], "next_page_token": "more"}

        client = _client({"a": endless})

        [read] = await _walk(client, ["a"], TaskListing(max_results=10, pages_max=2))

        assert client.list_tasks.await_count == 2
        assert (len(read.items), read.cut) == (2, True)

    async def test_a_list_that_fails_keeps_its_failure_and_the_others_answer(self) -> None:
        down = _Down("down")
        client = _client({"a": down, "b": {"items": [{"id": "t1"}]}})

        failed, answered = await _walk(client, ["a", "b"])

        assert failed.failure is down
        assert failed.items == []
        assert [task["id"] for task in answered.items] == ["t1"]

    async def test_a_list_failing_past_its_first_page_gives_nothing(self) -> None:
        """Half a list shown as a list would be a cut nobody stated."""

        def breaking(kwargs: dict[str, Any]) -> dict[str, Any]:
            if kwargs["page_token"] is None:
                return {"items": [{"id": "first"}], "next_page_token": "p2"}
            raise _Down("down")

        client = _client({"a": breaking})

        [read] = await _walk(client, ["a"])

        assert read.items == []
        assert isinstance(read.failure, _Down)

    async def test_a_failure_the_caller_did_not_name_is_raised(self) -> None:
        client = _client({"a": ValueError("a defect, not a provider's refusal")})

        with pytest.raises(ValueError):
            await _walk(client, ["a"])

    async def test_every_call_runs_under_the_callers_seam(self) -> None:
        """The Tools translate and count a provider failure there: it is what a list fails on."""
        seen: list[str] = []

        @contextlib.asynccontextmanager
        async def seam() -> AsyncIterator[None]:
            seen.append("in")
            try:
                yield
            except ValueError as raw:
                raise _Down("translated") from raw

        client = _client({"a": ValueError("raw"), "b": {"items": []}})

        failed, answered = await _walk(client, ["a", "b"], guard=seam)

        assert seen == ["in", "in"]
        assert isinstance(failed.failure, _Down)
        assert answered.failure is None


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

        client = MagicMock(list_tasks=AsyncMock(side_effect=read))

        await _walk(client, [f"l{index}" for index in range(3 * TASK_LISTS_READ_CONCURRENCY)])

        assert 1 < peak <= TASK_LISTS_READ_CONCURRENCY


class TestEveryList:
    async def _every(self, client: MagicMock, **options: Any) -> EveryTaskList:
        return await read_every_task_list(
            client,
            TaskListing(max_results=10),
            **{"lists_max": 25, "failures": (_Down,), **options},
        )

    async def test_the_lists_are_listed_then_each_is_read(self) -> None:
        client = _client({"home": {"items": [{"id": "h1"}]}, "work": {"items": [{"id": "w1"}]}})

        every = await self._every(client)

        client.list_task_lists.assert_awaited_once_with(25)
        assert [entry["id"] for entry in every.lists] == ["home", "work"]
        assert [call.args for call in client.list_tasks.await_args_list] == [("home",), ("work",)]
        assert (every.partial, every.first_failure, every.unread) == (False, None, [])

    async def test_each_task_carries_its_own_lists_id_and_name(self) -> None:
        client = _client({"home": {"items": [{"id": "h1"}]}, "work": {"items": [{"id": "w1"}]}})

        every = await self._every(client)

        assert [
            (task["id"], task[FIELD_TASK_LIST_ID], task[FIELD_TASK_LIST_NAME])
            for task in every.tasks()
        ] == [("h1", "home", "HOME"), ("w1", "work", "WORK")]

    async def test_a_stamped_task_is_a_copy_the_read_keeps_what_the_client_gave(self) -> None:
        client = _client({"home": {"items": [{"id": "h1"}]}})

        every = await self._every(client)
        every.tasks()

        assert every.reads[0].items == [{"id": "h1"}]

    async def test_a_list_without_a_name_names_none_and_one_without_an_id_is_not_read(self) -> None:
        lists = {"items": [{"title": "ghost"}, {"id": "home", "title": ""}]}
        client = _client({"home": {"items": [{"id": "h1"}]}}, lists=lists)

        every = await self._every(client)

        assert [call.args for call in client.list_tasks.await_args_list] == [("home",)]
        assert [task[FIELD_TASK_LIST_NAME] for task in every.tasks()] == [None]

    async def test_a_list_that_failed_is_named_and_the_others_stand(self) -> None:
        down = _Down("down")
        client = _client({"home": down, "work": {"items": [{"id": "w1"}]}})

        every = await self._every(client)

        assert [task["id"] for task in every.tasks()] == ["w1"]
        assert every.first_failure is down
        assert [entry["id"] for entry in every.unread] == ["home"]
        assert every.partial is True

    async def test_no_task_is_never_told_on_a_list_nobody_read(self) -> None:
        """Nothing beside a failed list is that failure, whoever reads (ADR-303)."""
        down = _Down("down")
        every = await self._every(_client({"home": down, "work": {"items": []}}))

        with pytest.raises(_Down) as raised:
            every.tasks_or_failure()

        assert raised.value is down

    async def test_tasks_beside_a_failed_list_are_given(self) -> None:
        client = _client({"home": _Down("down"), "work": {"items": [{"id": "w1"}]}})

        every = await self._every(client)

        assert [task["id"] for task in every.tasks_or_failure()] == ["w1"]

    @pytest.mark.parametrize("pages", [{}, {"home": {"items": []}, "work": {"items": []}}])
    async def test_nothing_to_do_is_an_empty_read_not_a_failure(
        self, pages: dict[str, Any]
    ) -> None:
        every = await self._every(_client(pages))

        assert every.tasks_or_failure() == []

    def test_the_shared_contract_lets_a_list_fail_on_the_provider_never_on_a_defect(
        self,
    ) -> None:
        assert TimeoutError in PROVIDER_FAILURES
        assert not any(issubclass(KeyError, failure) for failure in PROVIDER_FAILURES)

    @pytest.mark.parametrize(
        ("reads", "more_lists", "partial"),
        [
            ([TaskListRead()], False, False),
            ([], False, False),
            ([TaskListRead()], True, True),
            ([TaskListRead(), TaskListRead(cut=True)], False, True),
            ([TaskListRead(failure=_Down()), TaskListRead()], False, True),
        ],
    )
    def test_more_may_exist_as_soon_as_something_was_not_read(
        self, reads: list[TaskListRead], more_lists: bool, partial: bool
    ) -> None:
        lists = [{"id": f"l{index}"} for index in range(len(reads))]

        assert EveryTaskList(lists=lists, reads=reads, more_lists=more_lists).partial is partial

    async def test_more_lists_than_were_read_is_said(self) -> None:
        lists = {"items": [{"id": "home", "title": "Home"}], "next_page_token": "next"}
        client = _client({"home": {"items": []}}, lists=lists)

        every = await self._every(client)

        assert (every.more_lists, every.partial) == (True, True)

    async def test_lists_that_cannot_be_listed_fail_as_the_client_fails(self) -> None:
        """With no list known nothing can be read: each caller says it in its own words."""
        client = _client({})
        client.list_task_lists = AsyncMock(side_effect=_Down("down"))

        with pytest.raises(_Down):
            await self._every(client)

        client.list_tasks.assert_not_awaited()

    async def test_the_listing_of_the_lists_runs_under_the_callers_seam_too(self) -> None:
        seen: list[str] = []

        @contextlib.asynccontextmanager
        async def seam() -> AsyncIterator[None]:
            seen.append("in")
            yield

        client = _client({"home": {"items": []}})

        await self._every(client, guard=seam)

        assert seen == ["in", "in"]
