"""What the assistant reads of a person's tasks: every list, or the one named (2026-11-10).

With no list named the read takes every list of the account through the one walk
(``connectors/clients/task_lists``); its caller puts them in one order across the lists
(``core.task_due.in_due_order``: the earliest due first, the undated last). A list the model
names is read alone, in the provider's own order (the person's). Either way each task carries
its own list's real id and name: an act on it runs there, a card names it.

What was not read is said, never passed over (ADR-185, ADR-303): a list that failed is named,
a read cut at its bound says more exist, and a read where nothing came back beside a failed
list is that failure — « no task » is never told on a list nobody read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC
from typing import Any

from src.core.constants import TASK_LISTS_READ_MAX
from src.core.field_names import FIELD_TASK_LIST_ID, FIELD_TASK_LIST_NAME
from src.core.task_due import in_due_order
from src.core.time_utils import now_in_timezone
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.task_list_scope import named_task_list, names_a_list
from src.domains.connectors.clients.protocols import TasksClientProtocol
from src.domains.connectors.clients.task_lists import (
    PROVIDER_FAILURES,
    TaskListing,
    read_every_task_list,
    read_task_lists,
)


@dataclass(frozen=True, slots=True)
class TasksRead:
    """What a read of the person's tasks gave.

    Attributes:
        tasks: The tasks, each carrying its own list's id and name.
        list_id: The one list read; None when every list was.
        more_exist: A bound cut the read: a list's page, the lists read, or the answer's size.
        unread_lists: The names of the lists that could not be read.
    """

    tasks: list[dict[str, Any]]
    list_id: str | None = None
    more_exist: bool = False
    unread_lists: list[str] = field(default_factory=list)

    def shown(
        self, limit: int, *, timezone: str, only_completed: bool = False
    ) -> tuple[list[dict[str, Any]], bool]:
        """What an answer shows of the read, and whether more exist than it shows.

        Several lists stand in one order, the home's and the Tools' own (the earliest due
        first, the undated last); a list read alone keeps the provider's, the person's.

        Args:
            limit: The tasks an answer holds.
            timezone: The account's zone, which a To Do due is read in.
            only_completed: Keep the tasks that are done, and nothing else.

        Returns:
            The tasks shown, and whether a bound left some out.
        """
        tasks = self.tasks
        if only_completed:
            tasks = [task for task in tasks if task.get("status") == "completed"]
        if self.list_id is None:
            tasks = in_due_order(tasks, now_in_timezone(timezone).tzinfo or UTC)
        return tasks[:limit], self.more_exist or len(tasks) > limit


async def read_tasks(
    client: TasksClientProtocol, given: str | None, listing: TaskListing
) -> TasksRead:
    """Read the tasks of the list named, or of every list.

    Args:
        client: The account's tasks client.
        given: What the model passed for the list, if anything.
        listing: What is asked of each list.

    Returns:
        The tasks read and what was not.

    Raises:
        ToolValidationError: The model named a list no list answers to.
        Exception: The provider's own failure, when it left nothing to show.
    """
    if given is not None and names_a_list(given):
        entry = await named_task_list(client, given)
        list_id = str(entry["id"])
        [read] = await read_task_lists(client, [list_id], listing, failures=())
        stamp = {FIELD_TASK_LIST_ID: list_id, FIELD_TASK_LIST_NAME: entry.get("title") or None}
        return TasksRead(
            tasks=[{**task, **stamp} for task in read.items], list_id=list_id, more_exist=read.cut
        )
    every = await read_every_task_list(
        client, listing, lists_max=TASK_LISTS_READ_MAX, failures=PROVIDER_FAILURES
    )
    return TasksRead(
        tasks=every.tasks_or_failure(),
        more_exist=every.more_lists or any(read.cut for read in every.reads),
        unread_lists=[str(entry.get("title") or entry["id"]) for entry in every.unread],
    )


def partial_read_note(*, more_exist: bool, unread_lists: list[str]) -> str:
    """What the model is told of what was not read, in technical English; empty when all was."""
    notes: list[str] = []
    if more_exist:
        notes.append(
            "More tasks exist than are returned here: name a list or narrow the request to "
            "read the others."
        )
    if unread_lists:
        notes.append(
            "These lists could not be read and are missing from the answer: "
            + ", ".join(unread_lists)
            + "."
        )
    return " ".join(notes)


def with_partial_note(output: UnifiedToolOutput, note: str) -> UnifiedToolOutput:
    """The answer, saying what was not read in the data the model reads (ADR-185).

    Args:
        output: The read's answer.
        note: What :func:`partial_read_note` worded; empty when everything was read.

    Returns:
        The same answer, its message and its data carrying the note when there is one.
    """
    if note:
        output.message = f"{output.message} {note}"
        output.structured_data = {**output.structured_data, "partial_note": note}
    return output


__all__ = ["TasksRead", "partial_read_note", "read_tasks", "with_partial_note"]
