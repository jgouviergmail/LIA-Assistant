"""LIA's tools in the person's ElevenLabs workspace: created whole, verified, repaired in place.

ONE door for both voice surfaces that put LIA's tools on an ElevenLabs agent —
the phone's WEBHOOK tools (ADR-290) and the live session's CLIENT tools
(ADR-300, ADR-373). Before a conversation opens on an agent, what the workspace
serves is read and held against what LIA would send today: a tool someone
edited on the portal is rewritten in place, a tool the workspace lost is
re-created in its position, and a set that cannot be made exact refuses the
conversation (owner decision 2026-11-11: never an agent with tools out of date
or incomplete).

Measured 2026-11-11 on a throwaway agent and throwaway tools (dev workspace):

- the workspace serves back every field LIA sent, unchanged — enums in their
  order, the webhook's header in clear — and ADDS its own defaults (execution
  mode, interruption settings, per-parameter metadata), so a tool holds LIA's
  body when everything LIA sent is served as sent (:func:`holds`);
- ``PATCH /tools/{id}`` REPLACES the tool's config under the same id, a field
  set by hand falling back to the vendor's default;
- a tool deleted with force is taken off every agent silently, and naming it in
  an agent PATCH answers 404.

This module lives in ``telephony`` beside the client both surfaces already
share; ``live`` imports it, ``telephony`` never imports ``live``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import httpx
import structlog

from src.core.constants import TELEPHONY_LIVE_TOOL_PROVISIONING_CONCURRENCY
from src.domains.telephony.client import ElevenLabsAgentsError
from src.infrastructure.observability.metrics_live import live_agent_tools_repaired_total

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, Sequence

    from src.domains.telephony.client import ElevenLabsAgentsClient, ToolKind

logger = structlog.get_logger(__name__)

#: Which voice surface a repair served, as the metric labels it.
RepairSurface = Literal["live", "phone"]
#: What a vendor operation may fail with: a refusal, or a request that never got an answer.
VENDOR_FAILURES: tuple[type[Exception], ...] = (ElevenLabsAgentsError, httpx.RequestError)


@dataclass(frozen=True, slots=True)
class SetRepair:
    """What a set became once held against the workspace.

    Attributes:
        ids: The set's tool ids, in the bodies' order, after the repair.
        recreated: The ids created to stand where a lost tool stood.
        rewritten: The ids rewritten in place because they had drifted.
    """

    ids: tuple[str, ...]
    recreated: tuple[str, ...]
    rewritten: tuple[str, ...]


def agent_tool_ids(agent: dict[str, Any]) -> list[str]:
    """The tool ids an agent carries, as the vendor serves them (``prompt.tool_ids``).

    Args:
        agent: The agent as ``GET /agents/{id}`` returns it.

    Returns:
        The ids, in the vendor's order; empty when it names none.
    """
    config = agent.get("conversation_config")
    agent_block = config.get("agent") if isinstance(config, dict) else None
    prompt = agent_block.get("prompt") if isinstance(agent_block, dict) else None
    ids = prompt.get("tool_ids") if isinstance(prompt, dict) else None
    return [str(tool_id) for tool_id in ids or [] if isinstance(tool_id, str)]


def holds(served: object, sent: object) -> bool:
    """Whether the workspace serves everything LIA sent, as LIA sent it.

    A mapping holds when every key LIA sent is served, holding what was sent —
    the keys the vendor adds are its own defaults, never LIA's to compare. A
    list holds item by item (an enum's order, a required list). A boolean is
    never read as a number, and the same number is the same value.

    Args:
        served: What the workspace serves (a tool's ``tool_config``, or a part of it).
        sent: What LIA sends for it.

    Returns:
        True when nothing LIA sent was changed or lost.
    """
    if isinstance(sent, dict):
        return isinstance(served, dict) and all(
            key in served and holds(served[key], value) for key, value in sent.items()
        )
    if isinstance(sent, list):
        return (
            isinstance(served, list)
            and len(served) == len(sent)
            and all(holds(item, expected) for item, expected in zip(served, sent, strict=True))
        )
    if isinstance(sent, bool) or isinstance(served, bool):
        return served is sent
    return served == sent


async def read_workspace_tools(
    client: ElevenLabsAgentsClient, kind: ToolKind
) -> dict[str, dict[str, Any]]:
    """The workspace's tools of one kind, as the vendor serves them, by id.

    Args:
        client: The vendor client on the person's key.
        kind: The kind of tools to read.

    Returns:
        ``{tool id: tool_config}``.

    Raises:
        ElevenLabsAgentsError: On a vendor refusal.
        httpx.RequestError: When the listing got no answer.
    """
    return {
        str(tool["id"]): config
        for tool in await client.list_tools(kind)
        if isinstance(config := tool.get("tool_config"), dict)
    }


def _first_failure(group: BaseExceptionGroup[BaseException]) -> Exception:
    """The first refusal or lost request a ``TaskGroup`` gathered, nested groups walked."""
    for member in group.exceptions:
        if isinstance(member, VENDOR_FAILURES):
            return member
        if isinstance(member, BaseExceptionGroup):
            return _first_failure(member)
    raise AssertionError("no vendor failure in the group")  # pragma: no cover


async def _bounded_all(calls: Sequence[Callable[[], Awaitable[None]]]) -> None:
    """Run every vendor call concurrently under the provisioning bound, all or none.

    On the first failure the siblings are cancelled and awaited, and the failure
    is raised as itself (never wrapped in a group).

    A ``TaskGroup``, never ``gather``: measured 2026-09-19 on dev, ``gather``
    raised on a refusal while fifty creations went on, and every tool created
    after the rollback was an orphan nobody recorded.
    """
    gate = asyncio.Semaphore(TELEPHONY_LIVE_TOOL_PROVISIONING_CONCURRENCY)

    async def _run(call: Callable[[], Awaitable[None]]) -> None:
        async with gate:
            await call()

    try:
        async with asyncio.TaskGroup() as group:
            for call in calls:
                group.create_task(_run(call))
    except* VENDOR_FAILURES as failures:
        raise _first_failure(failures) from None


async def create_tools(
    client: ElevenLabsAgentsClient, bodies: Sequence[dict[str, Any]]
) -> list[str]:
    """Create every tool, concurrently under the bound, all or nothing.

    Never leaves half a set behind: on a failure, what was created is removed
    (forced) before the failure is raised — a tool the caller never recorded
    would be orphaned in the person's workspace.

    Args:
        client: The vendor client on the person's key.
        bodies: The ``POST /tools`` bodies, in the set's order.

    Returns:
        The vendor ids, in the bodies' order.

    Raises:
        ElevenLabsAgentsError: The first refusal, once everything created was removed.
        httpx.RequestError: The first request that got no answer, likewise.
    """
    created: dict[int, str] = {}

    def _create(index: int, body: dict[str, Any]) -> Callable[[], Awaitable[None]]:
        async def _call() -> None:
            created[index] = await client.create_tool(body)

        return _call

    try:
        await _bounded_all([_create(index, body) for index, body in enumerate(bodies)])
    except VENDOR_FAILURES:
        # Every sibling is finished or cancelled here: the snapshot is complete.
        for tool_id in list(created.values()):
            await client.delete_tool(tool_id)
        raise
    return [created[index] for index in range(len(bodies))]


def _triage(
    ids: Sequence[str],
    bodies: Sequence[dict[str, Any]],
    served: Mapping[str, dict[str, Any]],
) -> tuple[list[int], list[int]]:
    """The positions of a set the workspace lost, then those that no longer hold LIA's body."""
    lost = [index for index, tool_id in enumerate(ids) if tool_id not in served]
    drifted = [
        index
        for index, tool_id in enumerate(ids)
        if tool_id in served and not holds(served[tool_id], bodies[index]["tool_config"])
    ]
    return lost, drifted


async def _rewrite_all(
    client: ElevenLabsAgentsClient,
    ids: Sequence[str],
    bodies: Sequence[dict[str, Any]],
    positions: Sequence[int],
) -> None:
    """Rewrite each tool at ``positions`` in place with LIA's body, under the bound."""

    def _rewrite(index: int) -> Callable[[], Awaitable[None]]:
        async def _call() -> None:
            await client.update_tool(ids[index], bodies[index])

        return _call

    await _bounded_all([_rewrite(index) for index in positions])


def _count_repair(surface: RepairSurface, *, lost: int, drifted: int, tool_count: int) -> None:
    """Count and log what a repair did; nothing for a set that held."""
    if not (lost or drifted):
        return
    live_agent_tools_repaired_total.labels(surface=surface, reason="lost").inc(lost)
    live_agent_tools_repaired_total.labels(surface=surface, reason="drifted").inc(drifted)
    logger.info(
        "elevenlabs_tool_set_repaired",
        surface=surface,
        recreated=lost,
        rewritten=drifted,
        tool_count=tool_count,
    )


async def repair_set(
    client: ElevenLabsAgentsClient,
    ids: Sequence[str],
    bodies: Sequence[dict[str, Any]],
    served: Mapping[str, dict[str, Any]],
    *,
    surface: RepairSurface,
) -> SetRepair:
    """Make every tool of a set hold exactly LIA's body, before an agent is handed it.

    A tool the workspace no longer serves is re-created in its position; a tool
    that no longer holds what LIA sends (edited on the portal, or a body LIA
    changed without a new set) is rewritten in place, under its id. Nothing is
    written for a tool that holds. All or nothing: on a failure the tools this
    repair created are removed before the failure is raised — the caller records
    the repaired ids only once this returned.

    Args:
        client: The vendor client on the person's key.
        ids: The set's recorded tool ids, aligned with ``bodies``.
        bodies: What LIA sends for each tool today.
        served: The workspace's tools of the set's kind (:func:`read_workspace_tools`).
        surface: The voice surface the set serves, for the count.

    Returns:
        The repaired set.

    Raises:
        ValueError: When ``ids`` and ``bodies`` are not aligned.
        ElevenLabsAgentsError: The first refusal, once the re-created tools were removed.
        httpx.RequestError: The first request that got no answer, likewise.
    """
    if len(ids) != len(bodies):
        raise ValueError("a set's ids and bodies must be aligned")
    lost, drifted = _triage(ids, bodies, served)
    created = await create_tools(client, [bodies[index] for index in lost]) if lost else []
    repaired = list(ids)
    for index, tool_id in zip(lost, created, strict=True):
        repaired[index] = tool_id
    try:
        await _rewrite_all(client, ids, bodies, drifted)
    except VENDOR_FAILURES:
        for tool_id in created:
            await client.delete_tool(tool_id)
        raise
    _count_repair(surface, lost=len(lost), drifted=len(drifted), tool_count=len(ids))
    return SetRepair(
        ids=tuple(repaired),
        recreated=tuple(created),
        rewritten=tuple(ids[index] for index in drifted),
    )


__all__ = [
    "VENDOR_FAILURES",
    "RepairSurface",
    "SetRepair",
    "agent_tool_ids",
    "create_tools",
    "holds",
    "read_workspace_tools",
    "repair_set",
]
