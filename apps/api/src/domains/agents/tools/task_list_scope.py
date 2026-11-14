"""Which list a tasks tool works in (owner rule, 2026-11-10).

- Reading takes EVERY list, unless the model names one.
- The list the connector's settings name as the default is where a NEW task goes when nobody
  names one, and nothing else.
- A list the model names, by its id or by its name, is that list or a refusal. It is never
  replaced by another: measured 2026-11-10, a list's own id was looked up as a NAME, found
  nowhere, and silently became the provider's default list — a task created where nobody asked.
- An act on a task that exists runs in the task's OWN list: the one named, else the one the
  conversation last looked the task up in (``last_lookup_items``, as an event finds its
  calendar), else the one that HOLDS it: every list is asked, the default one first. A task
  no list holds is said, never acted on in a list picked for it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any, Final
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime

from src.core.constants import TASK_LIST_NAMES_SCAN_MAX, TASK_LISTS_READ_CONCURRENCY
from src.core.exceptions import ConnectorAPIError, ResourceNotFoundError
from src.core.field_names import FIELD_TASK_LIST_ID
from src.domains.agents.constants import CONTEXT_DOMAIN_TASKS
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.exceptions import ToolValidationError
from src.domains.agents.tools.last_lookup import last_lookup_items
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.domains.connectors.clients.protocols import TasksClientProtocol
from src.domains.connectors.clients.task_lists import PROVIDER_FAILURES
from src.domains.connectors.preferences.owner_defaults import TASK_LIST, resolve_owner_task_list_id
from src.domains.connectors.preferences.resolver import preference_key
from src.domains.connectors.provider_resolver import resolve_active_connector

logger = structlog.get_logger(__name__)

#: What a model passes for « no list named »: the provider's alias, the tools' former default.
UNNAMED_LIST: Final = TASK_LIST.fallback
#: The parameter every tasks tool names a list by.
LIST_PARAMETER: Final = "task_list_id"

#: Said to the model, never to the person: technical English, no value echoed (ADR-256).
UNKNOWN_LIST: Final = (
    "No task list answers to this id or name. Read the account's lists with "
    "list_task_lists_tool, then pass the id or the exact name of one of them."
)
AMBIGUOUS_LIST: Final = (
    "Several task lists answer to this name. Pass the id of the one meant: "
    "list_task_lists_tool gives each list's id."
)
UNKNOWN_TASK: Final = (
    "No task list holds a task with this id. Read the tasks again with get_tasks_tool, "
    "then pass an id it returns."
)

#: What a list answers for a task it does not hold. Measured on Graph (2026-11-10): 404 for
#: an id nobody has, 400 for the id of ANOTHER list's task (a To Do id names its own list).
_NOT_IN_THIS_LIST: Final = frozenset({400, 404})


def names_a_list(given: str | None) -> bool:
    """Whether the model named a list, rather than leaving it out or passing the alias."""
    return bool(given) and given != UNNAMED_LIST


async def named_task_list(client: TasksClientProtocol, given: str) -> dict[str, Any]:
    """The list an id or a name designates.

    Args:
        client: The account's tasks client.
        given: What the model passed: a list's id, or its name (whatever its case).

    Returns:
        The list, as the provider lists it (``id``, ``title``).

    Raises:
        ToolValidationError: No list answers to it, or several lists share that name.
    """
    listed = await client.list_task_lists(max_results=TASK_LIST_NAMES_SCAN_MAX)
    lists: list[dict[str, Any]] = [entry for entry in listed.get("items") or [] if entry.get("id")]
    by_id = [entry for entry in lists if entry["id"] == given]
    exact = [entry for entry in lists if entry.get("title") == given]
    loose = [
        entry
        for entry in lists
        if preference_key(str(entry.get("title") or "")) == preference_key(given)
    ]
    matches = by_id or exact or loose
    if not matches:
        raise ToolValidationError(UNKNOWN_LIST, field=LIST_PARAMETER)
    if len(matches) > 1:
        raise ToolValidationError(AMBIGUOUS_LIST, field=LIST_PARAMETER)
    return matches[0]


async def default_task_list_id(client: Any, user_id: UUID) -> str:
    """Where a new task goes when nobody names a list: the settings' default, else the provider's.

    The broad catch is this call site's own and deliberate: the shared resolver lets an
    infrastructure failure propagate, and a task created in the provider's default list rather
    than not at all is the lesser harm here.

    Args:
        client: The account's tasks client (it carries its connector service).
        user_id: The account.

    Returns:
        A list id, or the provider's alias for its default list.
    """
    try:
        resolved_type = await resolve_active_connector(user_id, "tasks", client.connector_service)
        if resolved_type:
            return await resolve_owner_task_list_id(
                client=client, owner_id=user_id, connector_type=resolved_type
            )
    except Exception as failure:  # noqa: BLE001 - see the docstring
        logger.warning("tasks_preference_resolution_failed", error_type=type(failure).__name__)
    return UNNAMED_LIST


async def new_task_list(client: Any, user_id: UUID, given: str | None) -> dict[str, Any]:
    """The list a NEW task goes in: the one named, else the default one.

    Args:
        client: The account's tasks client.
        user_id: The account.
        given: What the model passed for the list, if anything.

    Returns:
        ``id`` and ``title``; the title is None when the default list's own could not be read
        (the task is created all the same, and its card names no list).

    Raises:
        ToolValidationError: The model named a list no list answers to.
    """
    if given is not None and names_a_list(given):
        return await named_task_list(client, given)
    list_id = await default_task_list_id(client, user_id)
    try:
        listed = await client.get_task_list(list_id)
    except Exception as failure:  # noqa: BLE001 - the name is for the card; the task still goes
        logger.debug("default_task_list_name_unread", error_type=type(failure).__name__)
        return {"id": list_id, "title": None}
    return {"id": str(listed.get("id") or list_id), "title": listed.get("title") or None}


async def looked_up_task_list_ids(
    runtime: ToolRuntime[LiaRuntimeContext, Any] | None, tool_name: str
) -> dict[str, str]:
    """The list of each task the conversation last looked up, by task id.

    Args:
        runtime: The tool's runtime; without one nothing is known.
        tool_name: The tool asking, for the validation's own log.

    Returns:
        Task id to list id, for the tasks whose list is known.
    """
    if runtime is None:
        return {}
    config = validate_runtime_config(runtime, tool_name)
    if isinstance(config, UnifiedToolOutput):
        return {}
    found: dict[str, str] = {}
    for item in await last_lookup_items(config, CONTEXT_DOMAIN_TASKS):
        task_id, list_id = item.get("id") or item.get("task_id"), item.get(FIELD_TASK_LIST_ID)
        if isinstance(task_id, str) and isinstance(list_id, str) and list_id:
            found.setdefault(task_id, list_id)
    return found


async def task_list_ids_of(
    client: Any,
    user_id: UUID,
    task_ids: list[str],
    given: str | None,
    *,
    runtime: ToolRuntime[LiaRuntimeContext, Any] | None,
    tool_name: str,
) -> dict[str, str]:
    """The list each of these tasks lives in.

    Args:
        client: The account's tasks client.
        user_id: The account.
        task_ids: The tasks an act or a fetch is about.
        given: What the model passed for the list, if anything.
        runtime: The tool's runtime, whose conversation remembers what it looked up.
        tool_name: The tool asking.

    Returns:
        Task id to list id: the list named for all of them, else each task's own as the
        conversation read it, else the list found to hold it. A task no list holds is
        LEFT OUT: its caller says so, one task at a time.

    Raises:
        ToolValidationError: The model named a list no list answers to.
        Exception: A list could not be asked while a task is still not found.
    """
    if given is not None and names_a_list(given):
        named = str((await named_task_list(client, given))["id"])
        return dict.fromkeys(task_ids, named)
    known = await looked_up_task_list_ids(runtime, tool_name)
    unknown = [task_id for task_id in task_ids if task_id not in known]
    found = await find_task_lists(client, user_id, unknown) if unknown else {}
    lists = {**found, **known}
    return {task_id: lists[task_id] for task_id in task_ids if task_id in lists}


async def _holds(client: Any, list_id: str, task_id: str) -> bool:
    """Whether a list holds a task: asked of the provider, its « not here » read as no."""
    try:
        await client.get_task(list_id, task_id)
    except ResourceNotFoundError:
        return False
    except ConnectorAPIError as answer:
        if answer.status_code not in _NOT_IN_THIS_LIST:
            raise
        return False
    return True


async def find_task_lists(client: Any, user_id: UUID, task_ids: Sequence[str]) -> dict[str, str]:
    """The list each of these tasks lives in, when nothing says it: every list is asked.

    Owner rule, 2026-11-10: the default list is where a new task goes, never where a task
    is assumed to be. It is asked FIRST (a task made with no list named went there), then
    the others in the provider's order, and the asking stops once every task is found.

    Args:
        client: The account's tasks client.
        user_id: The account.
        task_ids: The tasks whose list nobody named and the conversation never read.

    Returns:
        Task id to list id, for the tasks some list holds.

    Raises:
        Exception: A list could not be asked while a task is still not found: « no list
            holds it » is never told on a list nobody could look in (ADR-303).
    """
    listed = await client.list_task_lists(max_results=TASK_LIST_NAMES_SCAN_MAX)
    default = await default_task_list_id(client, user_id)
    list_ids = sorted(
        (str(entry["id"]) for entry in listed.get("items") or [] if entry.get("id")),
        key=lambda list_id: list_id != default,
    )
    gate = asyncio.Semaphore(TASK_LISTS_READ_CONCURRENCY)

    async def asked(list_id: str, task_id: str) -> bool | Exception:
        async with gate:
            try:
                return await _holds(client, list_id, task_id)
            except PROVIDER_FAILURES as failure:
                return failure

    found: dict[str, str] = {}
    unasked: Exception | None = None
    for list_id in list_ids:
        missing = [task_id for task_id in task_ids if task_id not in found]
        if not missing:
            break
        answers = await asyncio.gather(*(asked(list_id, task_id) for task_id in missing))
        for task_id, answer in zip(missing, answers, strict=True):
            if answer is True:
                found[task_id] = list_id
            elif isinstance(answer, Exception):
                unasked = unasked or answer
    if unasked is not None and any(task_id not in found for task_id in task_ids):
        raise unasked
    return found


async def task_list_id_of(
    client: Any,
    user_id: UUID,
    task_id: str,
    given: str | None,
    *,
    runtime: ToolRuntime[LiaRuntimeContext, Any] | None,
    tool_name: str,
) -> str:
    """The list one task lives in (see :func:`task_list_ids_of`).

    Raises:
        ToolValidationError: The model named a list no list answers to, or no list holds
            the task: an act is never run in a list picked for it.
    """
    lists = await task_list_ids_of(
        client, user_id, [task_id], given, runtime=runtime, tool_name=tool_name
    )
    if task_id not in lists:
        raise ToolValidationError(UNKNOWN_TASK, field="task_id")
    return lists[task_id]


async def own_task_list_id(
    client: Any,
    user_id: UUID,
    task_id: str,
    kwargs: Mapping[str, Any],
    *,
    runtime: ToolRuntime[LiaRuntimeContext, Any] | None,
    tool_name: str,
) -> str:
    """The list a task lives in, from what a tool was called with.

    Args:
        client: The account's tasks client.
        user_id: The account.
        task_id: The task.
        kwargs: The tool's own arguments, where the model may have named a list.
        runtime: The TOOL's runtime (``self.runtime``): ``execute_api_call`` never
            receives it among its arguments.
        tool_name: The tool asking.

    Returns:
        The list id (see :func:`task_list_ids_of`).
    """
    return await task_list_id_of(
        client,
        user_id,
        task_id,
        kwargs.get(LIST_PARAMETER),
        runtime=runtime,
        tool_name=tool_name,
    )


__all__ = [
    "AMBIGUOUS_LIST",
    "LIST_PARAMETER",
    "UNKNOWN_LIST",
    "UNKNOWN_TASK",
    "UNNAMED_LIST",
    "default_task_list_id",
    "find_task_lists",
    "looked_up_task_list_ids",
    "named_task_list",
    "names_a_list",
    "new_task_list",
    "own_task_list_id",
    "task_list_id_of",
    "task_list_ids_of",
]
