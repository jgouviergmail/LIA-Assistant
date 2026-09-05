"""Asking instead of failing, and replaying once the answer comes (ADR-263).

A tool whose declared policy demands a confirmation and that builds no draft of
its own — a third-party MCP tool whose server asks for one — used to run
UNCONFIRMED in the pipeline (defect H2). The gate alone would have made it
unrunnable there instead, which is not safety but a capability lost.

So the gate hands the call back as a DRAFT, the one shape both execution modes
already know how to confirm, and this module holds the two halves of that
handoff:

- :func:`confirmation_draft` builds it, reusing ``DraftService`` exactly as the
  25 draft-producing tools do — the card, the queueing, the batch handling and
  the resume all come for free;
- :func:`execute_tool_call_draft` replays the call once the user has approved,
  under a scope that says so.

The replay executor is deliberately NOT ledgered itself: the tool's own gate
records the effect under its real policy. Two rows would make the register lie
about how much happened, and — worse — both would share the scope key, so the
inner call would be mistaken for a replay and never run at all.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog

from src.domains.agents.drafts.models import DraftType
from src.domains.agents.effects.scope import EffectScope, current_scope, effect_scope

logger = structlog.get_logger(__name__)


def confirmation_draft(tool_name: str, tool_args: dict[str, Any]) -> Any:
    """Build the draft that asks the user to allow ``tool_name``.

    Args:
        tool_name: The tool the model wants to run.
        tool_args: The arguments it chose. Kept whole in the draft — the replay
            must be the call the user approved, not a shortened version of it.

    Returns:
        A ``UnifiedToolOutput`` carrying ``requires_confirmation=True``, which
        every existing draft path already understands.
    """
    from src.domains.agents.drafts.service import DraftService

    return DraftService().create_draft(
        draft_type=DraftType.TOOL_CALL,
        content={
            # No id of our own: ``DraftService`` assigns the one the card, the
            # resume and the ledger all name. A second identity for one
            # operation is how two records of one effect begin.
            "tool_name": tool_name,
            "tool_label": _readable_tool_name(tool_name),
            "tool_args": tool_args,
        },
        source_tool=tool_name,
    )


def _readable_tool_name(tool_name: str) -> str:
    """Turn a registered tool name into something a card can show.

    Args:
        tool_name: e.g. ``mcp_era_cancel_subscription`` or ``delete_event_tool``.

    Returns:
        e.g. ``era: cancel subscription`` / ``delete event``. Cosmetic only: the
        replay always uses the registered name.
    """
    from src.core.constants import MCP_TOOL_NAME_PREFIX

    name = tool_name.removesuffix("_tool")
    if name.startswith(f"{MCP_TOOL_NAME_PREFIX}_"):
        server, _, rest = name[len(MCP_TOOL_NAME_PREFIX) + 1 :].partition("_")
        return f"{server}: {_spaced(rest)}" if rest else server
    return _spaced(name)


def _spaced(name: str) -> str:
    """Turn a snake_case fragment into words.

    ``split()`` rather than a plain ``replace``: MCP servers namespace their
    tools with a DOUBLE underscore (``billing__cancel_subscription``), which a
    naive replace turns into a double space on the card the user reads.
    """
    return " ".join(name.replace("_", " ").split())


async def execute_tool_call_draft(
    draft_content: dict[str, Any], user_id: uuid.UUID, deps: Any
) -> dict[str, Any]:
    """Replay the confirmed call (ADR-263).

    Runs the tool through its NORMAL gated coroutine, under a scope that
    carries the user's approval — so the effect is claimed, performed and
    closed exactly once, by the gate that knows the tool's real policy.

    Args:
        draft_content: ``{tool_name, tool_args, draft_id}`` from the draft.
        user_id: The acting user (the gate reads identity from the run context;
            this is part of the executor contract shared by 19 executors).
        deps: Tool dependency container, unused here — the tool resolves its own
            dependencies from the run context, as it does on the first attempt.

    Returns:
        The tool's own result, or a failure payload naming what went wrong.
    """
    from src.domains.agents.tools.tool_registry import get_tool

    tool_name = str(draft_content.get("tool_name") or "")
    tool_args = draft_content.get("tool_args") or {}
    draft_id = str(draft_content.get("draft_id") or uuid.uuid4().hex)

    tool = get_tool(tool_name)
    coroutine = getattr(tool, "coroutine", None)
    if tool is None or coroutine is None:
        # The catalogue changed between the question and the answer: say so
        # rather than pretending the action happened.
        logger.warning("confirmed_tool_call_unresolved", tool_name=tool_name)
        return {
            "success": False,
            "error": f"Tool '{tool_name}' is no longer available; nothing was performed.",
        }

    # The draft executor already published an APPROVED scope keyed by the real
    # draft id — reuse it rather than invent a second identity for one
    # operation. The fallback covers a direct call (a test, a future caller):
    # the effect must still be claimed under something stable.
    ambient = current_scope()
    scope = (
        ambient
        if ambient is not None and ambient.approved
        else EffectScope(
            run_id=draft_id,
            idempotency_key=f"call:{draft_id}",
            source="user",
            approved=True,
            approval_kind="draft_critique",
            approval_ref=draft_id,
        )
    )
    logger.info("confirmed_tool_call_replayed", tool_name=tool_name)
    with effect_scope(scope):
        result: dict[str, Any] = await coroutine(**tool_args)
    return result
