"""The tasks of every list for a discussion read, each fenced by its own list (2026-11-10).

Whoever reads a person's tasks reads ALL their lists (owner rule): the list a connector's
settings name as the default is where a NEW task goes when nobody names one, and nothing else.
A discussion read keeps what makes it one:

- each list is its own CONTAINER: a task's reference is minted under its list's scope and read
  back there only, so a reference never reaches another list's task, nor another account's;
- the read's physical-call budget bounds the lists read (one call lists them, one reads each):
  an account holding more, a list cut at its page or one the budget stopped makes the page
  TRUNCATED, never complete;
- a provider's failure stays the READ's failure: the gateway turns it into a closed source or a
  backoff, which a list silently set aside would hide;
- a task's text is the provider's record, unchanged: an admitted fact keeps its version.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC
from typing import Final

from src.core.constants import TASK_LIST_NAMES_SCAN_MAX
from src.core.field_names import FIELD_TASK_LIST_ID
from src.core.read_budget import ReadCallLimit
from src.core.task_due import in_due_order
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.task_lists import TaskListing, read_every_task_list
from src.domains.connectors.discussion_authority import require_reader_authorities
from src.domains.connectors.discussion_projections import provider_identifier, task_evidence
from src.domains.connectors.preferences.owner_defaults import TASK_LIST
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    SourceKey,
    SourceReadRequest,
    SourceSnapshot,
    source_snapshot,
)

#: What one list may stop on while the others stand: the read's own call budget, nothing else.
_BUDGET_STOP: Final[tuple[type[Exception], ...]] = (ReadCallLimit,)
#: The scope a read carries when it names no container: what must not move while reading.
_NO_CONTAINER: Final = ""


async def read_discussion_tasks(request: SourceReadRequest, opened: ActiveClient) -> SourceSnapshot:
    """Read one task by its reference, or the tasks of every list (due in the window when future).

    A query filters the page read; it does not search the provider.

    Args:
        request: The bounded read.
        opened: The account's tasks client, open for the length of the read.

    Returns:
        The page, each task fenced by the scope of its own list.

    Raises:
        ValueError: The reference belongs to no list of this account, or the account or its
            permissions changed while reading.
    """
    before = await _scope(request, opened)
    page = await (_referenced if request.request.reference else _listed)(request, opened)
    if await _scope(request, opened) != before:
        raise ValueError("connector account or permissions changed while reading")
    return page


async def _authorities(
    request: SourceReadRequest, opened: ActiveClient, containers: Iterable[str]
) -> dict[str, str]:
    return await require_reader_authorities(
        request.owner_id, opened.connector_type, opened.client, containers
    )


async def _scope(request: SourceReadRequest, opened: ActiveClient) -> str:
    return (await _authorities(request, opened, (_NO_CONTAINER,)))[_NO_CONTAINER]


async def _listed(request: SourceReadRequest, opened: ActiveClient) -> SourceSnapshot:
    """The tasks of every list the read's budget reaches, the earliest due first."""
    future = request.request.operation == "future"
    every = await read_every_task_list(
        opened.client,
        TaskListing(
            max_results=request.item_limit + 1,
            show_completed=True,
            due_min=request.window_start.isoformat() if future else None,
            due_max=request.window_end.isoformat() if future else None,
        ),
        # One call lists the lists, one reads each: the read's own budget is the bound.
        lists_max=max(1, request.call_limit - 1),
        failures=_BUDGET_STOP,
    )
    accounts = await _authorities(request, opened, (str(entry["id"]) for entry in every.lists))
    tasks = in_due_order(every.tasks_or_failure(), request.now.tzinfo or UTC)
    items = [
        task_evidence(
            task,
            account=accounts[task[FIELD_TASK_LIST_ID]],
            now=request.now,
            chars=request.item_max_chars,
        )
        for task in tasks[: request.item_limit]
    ]
    return _page(request, items, truncated=every.partial or len(tasks) > request.item_limit)


async def _referenced(request: SourceReadRequest, opened: ActiveClient) -> SourceSnapshot:
    """The one task a reference names, read in the list it was minted under."""
    listed = await opened.client.list_task_lists(TASK_LIST_NAMES_SCAN_MAX)
    containers = [str(entry["id"]) for entry in listed.get("items") or [] if entry.get("id")]
    # The provider's alias too: a reference minted while one list was read, with no default
    # list configured, was fenced under that name.
    accounts = await _authorities(request, opened, (*containers, TASK_LIST.fallback))
    container, account, identifier = _container_of(str(request.request.reference), accounts)
    raw: object = await opened.client.get_task(container, identifier)
    evidence = task_evidence(raw, account=account, now=request.now, chars=request.item_max_chars)
    return _page(request, [evidence], truncated=False)


def _container_of(reference: str, accounts: Mapping[str, str]) -> tuple[str, str, str]:
    """The list a reference was minted under: its id, its scope, and the task's own id.

    Raises:
        ValueError: No list of this account answers to the reference (another account's, a
            list that is gone, or no reference at all).
    """
    for container, account in accounts.items():
        try:
            return container, account, provider_identifier(reference, SourceKey.TASKS, account)
        except ValueError:
            continue
    raise ValueError("provider reference belongs to no task list of this account")


def _page(
    request: SourceReadRequest, items: Sequence[DiscussionEvidence], *, truncated: bool
) -> SourceSnapshot:
    page = source_snapshot(
        request,
        status="truncated" if truncated else "ok" if items else "empty",
        items=tuple(items),
        complete=False,
        coverage_kind="active_facts",
    )
    query = request.request.query
    if not query:
        return page
    kept = tuple(item for item in page.items if query.casefold() in item.excerpt.casefold())
    return page.model_copy(update={"items": kept})


__all__ = ["read_discussion_tasks"]
