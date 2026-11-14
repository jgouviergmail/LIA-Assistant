"""Every task list of an account read in one go, a few lists at a time (2026-11-10).

Whoever reads a person's tasks reads ALL their lists (owner rule, 2026-11-10): the Tools' views
across the lists, the home's tasks card, the assistant's tools, the heartbeat, the radio, a
peer's shared titles, the discussions' tasks source. The list a connector's settings name as
the default is where a NEW task goes when nobody names one, and nothing else. One walk serves
every reader, so the burst a provider accepts is decided once
(``TASK_LISTS_READ_CONCURRENCY``). A list that could not be read keeps its failure and the
others answer; a list holding more than the pages read says so (ADR-185).

Each caller keeps its own failure contract: the errors a list may fail on, and the seam every
provider call runs under (the Tools count and translate theirs through ``provider_call``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager, nullcontext
from dataclasses import dataclass, field
from typing import Any, Final

import httpx

from src.core.constants import TASK_LISTS_READ_CONCURRENCY
from src.core.exceptions import BaseAPIException, MaxRetriesExceededError
from src.core.field_names import FIELD_TASK_LIST_ID, FIELD_TASK_LIST_NAME
from src.domains.connectors.clients.protocols import TasksClientProtocol

#: What one list may fail on while the others answer, for a reader with no narrower
#: contract of its own (the assistant, the heartbeat, the radio): the provider's refusals
#: and its silence. Anything else is a defect, and is raised.
PROVIDER_FAILURES: Final[tuple[type[Exception], ...]] = (
    BaseAPIException,
    MaxRetriesExceededError,
    httpx.HTTPError,
    TimeoutError,
)


@dataclass(frozen=True, slots=True)
class TaskListing:
    """What is asked of each list.

    Attributes:
        max_results: The tasks one page asks for.
        pages_max: The pages read of one list; a list holding more is ``cut``.
        show_completed: Include the tasks that are done.
        show_hidden: Include the done tasks a provider hides from its own listing.
        due_min: Keep the tasks due from this RFC 3339 instant.
        due_max: Keep the tasks due up to this RFC 3339 instant (the undated leave with it).
        completed_min: Keep the tasks done from this RFC 3339 instant.
    """

    max_results: int
    pages_max: int = 1
    show_completed: bool = False
    show_hidden: bool = False
    due_min: str | None = None
    due_max: str | None = None
    completed_min: str | None = None


@dataclass(frozen=True, slots=True)
class TaskListRead:
    """What one list gave: its tasks and whether it holds more, or why it gave nothing.

    Attributes:
        items: The tasks read, as the client answers them (Google Tasks' shape).
        cut: The list holds more than the pages read.
        failure: Why the list could not be read; None when it was.
    """

    items: list[dict[str, Any]] = field(default_factory=list)
    cut: bool = False
    failure: Exception | None = None


@dataclass(frozen=True, slots=True)
class EveryTaskList:
    """What every list of an account gave.

    Attributes:
        lists: The lists read, as the provider lists them (``id``, ``title``).
        reads: What each gave, in the same order.
        more_lists: The account holds more lists than were read.
    """

    lists: list[dict[str, Any]]
    reads: list[TaskListRead]
    more_lists: bool = False

    @property
    def first_failure(self) -> Exception | None:
        """Why a list could not be read, the first that failed; None when every list answered."""
        return next((read.failure for read in self.reads if read.failure is not None), None)

    @property
    def partial(self) -> bool:
        """Whether more may exist: a list unread or cut, or lists beyond those read."""
        return self.more_lists or any(read.failure is not None or read.cut for read in self.reads)

    @property
    def unread(self) -> list[dict[str, Any]]:
        """The lists that could not be read."""
        return [
            entry
            for entry, read in zip(self.lists, self.reads, strict=True)
            if read.failure is not None
        ]

    def tasks(self) -> list[dict[str, Any]]:
        """Every task read, each a copy carrying its own list's id and name, list after list."""
        return [
            {
                **task,
                FIELD_TASK_LIST_ID: str(entry["id"]),
                FIELD_TASK_LIST_NAME: entry.get("title") or None,
            }
            for entry, read in zip(self.lists, self.reads, strict=True)
            for task in read.items
        ]

    def tasks_or_failure(self) -> list[dict[str, Any]]:
        """Every task read, or the failure that left nothing to show.

        « No task » is never told on a list nobody could read (ADR-303): with nothing
        beside a failed list, the read is that failure.

        Returns:
            The tasks, as :meth:`tasks` gives them; empty only when every list answered
            or the account holds none.

        Raises:
            Exception: The first list's failure, when no task came back.
        """
        tasks = self.tasks()
        if not tasks and (failure := self.first_failure) is not None:
            raise failure
        return tasks


async def read_every_task_list(
    client: TasksClientProtocol,
    listing: TaskListing,
    *,
    lists_max: int,
    failures: tuple[type[Exception], ...],
    guard: Callable[[], AbstractAsyncContextManager[None]] = nullcontext,
) -> EveryTaskList:
    """List the account's task lists, then read each of them.

    The listing of the lists itself runs under the caller's seam and fails as the client
    fails: with no list known there is nothing to read, and each caller says that in its own
    words.

    Args:
        client: The account's tasks client, open for the length of the read.
        listing: What is asked of each list.
        lists_max: The lists read; an account holding more says so (``more_lists``).
        failures: What a list may fail on without failing the others.
        guard: The seam one provider call runs under.

    Returns:
        The lists that carry an id and what each gave.
    """
    async with guard():
        listed = await client.list_task_lists(lists_max)
    lists = [entry for entry in listed.get("items") or [] if entry.get("id")]
    reads = await read_task_lists(
        client, [str(entry["id"]) for entry in lists], listing, failures=failures, guard=guard
    )
    return EveryTaskList(lists=lists, reads=reads, more_lists=bool(listed.get("next_page_token")))


async def read_task_lists(
    client: TasksClientProtocol,
    list_ids: Sequence[str],
    listing: TaskListing,
    *,
    failures: tuple[type[Exception], ...],
    guard: Callable[[], AbstractAsyncContextManager[None]] = nullcontext,
) -> list[TaskListRead]:
    """Read the tasks of every list named, a few lists at a time.

    Args:
        client: The account's tasks client, open for the length of the read.
        list_ids: The lists, by their real ids.
        listing: What is asked of each list.
        failures: What a list may fail on without failing the others.
        guard: The seam one provider call runs under.

    Returns:
        One read per list, in the order given.
    """
    gate = asyncio.Semaphore(TASK_LISTS_READ_CONCURRENCY)

    async def bounded(list_id: str) -> TaskListRead:
        async with gate:
            return await _read_one(client, list_id, listing, failures=failures, guard=guard)

    return list(await asyncio.gather(*(bounded(list_id) for list_id in list_ids)))


async def _read_one(
    client: TasksClientProtocol,
    list_id: str,
    listing: TaskListing,
    *,
    failures: tuple[type[Exception], ...],
    guard: Callable[[], AbstractAsyncContextManager[None]],
) -> TaskListRead:
    """One list's tasks, or the failure that kept it unread."""
    items: list[dict[str, Any]] = []
    token: str | None = None
    try:
        for _page in range(listing.pages_max):
            async with guard():
                raw = await client.list_tasks(
                    list_id,
                    max_results=listing.max_results,
                    show_completed=listing.show_completed,
                    show_hidden=listing.show_hidden,
                    due_min=listing.due_min,
                    due_max=listing.due_max,
                    completed_min=listing.completed_min,
                    page_token=token,
                )
            items += raw.get("items") or []
            token = raw.get("next_page_token") or None
            if token is None:
                break
    except failures as failure:
        return TaskListRead(failure=failure)
    return TaskListRead(items=items, cut=token is not None)


__all__ = [
    "PROVIDER_FAILURES",
    "EveryTaskList",
    "TaskListRead",
    "TaskListing",
    "read_every_task_list",
    "read_task_lists",
]
