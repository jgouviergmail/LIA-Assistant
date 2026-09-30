"""What a raw tool result SAYS, read once for every reader of the ReAct loop.

The loop reads four facts off the value a tool returned, before its string
conversion: whether the call produced anything (ADR-248 — what buys an
iteration), whether the tool DECLARED a failure (ADR-303 — the structural
marker the ``ToolMessage`` carries), whether the call never ran at all (the
egress question's refusal, ADR-298) and which skill an activation handed
over (ADR-327 — what the response node's runner must not run again). Each
is ONE predicate, so the loop, the response node and their tests cannot
disagree on a payload.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.core.tool_outcome import explicit_success
from src.domains.agents.utils.message_filters import TOOL_CALL_NOT_RUN


def activated_skill_of(raw_result: Any) -> str | None:
    """The skill a successful activation answered with, or None (ADR-327).

    ``activate_skill_tool`` names the skill in its metadata
    (``{"skill_name": …, "activation": …}``) whether it handed the person's own
    instructions over or ran a third-party skill in its isolated runner; that
    name is what the response node needs to know the loop already ran it.

    Args:
        raw_result: The tool's return value, before string conversion.

    Returns:
        The activated skill's name, or None for any other result.
    """
    if isinstance(raw_result, Mapping):
        success, metadata = raw_result.get("success"), raw_result.get("tool_metadata")
    else:
        success = getattr(raw_result, "success", None)
        metadata = getattr(raw_result, "tool_metadata", None)
    if success is not True or not isinstance(metadata, Mapping) or not metadata.get("activation"):
        return None
    name = metadata.get("skill_name")
    return name if isinstance(name, str) and name else None


def is_productive_result(raw_result: Any) -> bool:
    """Did this tool call actually bring something back?

    Productivity is what buys more iterations (ADR-248), so it must mean
    "the context learned something", never "a call was attempted". A declared
    failure and an empty result both teach the loop nothing it can build on.

    Args:
        raw_result: The tool's return value, before string conversion.

    Returns:
        True when the call produced usable content.
    """
    if raw_result is None:
        return False
    if not explicit_success(raw_result):
        # ``UnifiedToolOutput.failure(...)`` is a Pydantic model, so the old
        # dict-only branch never saw it and ``bool(model)`` was always True: a
        # loop failing every call bought itself iterations up to the ceiling,
        # which this function's own contract forbids (ADR-303).
        return False
    # Whatever survived the failure check is productive iff it carries
    # something: an EMPTY container teaches the loop nothing either, which the
    # contract above states and the dict branch used to contradict — ``{}``
    # counted as production and extended the budget on nothing.
    return bool(raw_result)


def tool_message_status(raw_result: Any) -> str:
    """``"error"`` when the tool DECLARED a failure, else ``"success"``.

    The ReAct body carries the tool's PROSE (``compose_tool_message``), so the
    only honest way to tell a failure from an answer is a marker the message
    carries itself. ``ToolMessage.status`` is that marker — already used by the
    finalize node for abandoned calls (ADR-248) — and it is what the honesty
    directive reads. Before it, no ReAct failure ever reached that directive,
    and the model, left without a word about what broke, invented one. A call
    that never ran (:func:`call_artifact`) failed nothing.

    Args:
        raw_result: The tool's return value, before string conversion.

    Returns:
        ``"error"`` or ``"success"``.
    """
    ran = call_artifact(raw_result) is None
    return "success" if explicit_success(raw_result) or not ran else "error"


def call_artifact(raw_result: Any) -> str | None:
    """``TOOL_CALL_NOT_RUN`` when the answer says the call never ran, else None.

    The person refusing what the call asked for (the egress question) is a
    decision, never a failure: the answer carries the marker in its metadata,
    and the ToolMessage carries it on to every reader of outcomes.

    Args:
        raw_result: The tool's return value, before string conversion.

    Returns:
        The artifact the ToolMessage carries.
    """
    metadata = getattr(raw_result, "metadata", None)
    not_run = isinstance(metadata, dict) and metadata.get(TOOL_CALL_NOT_RUN) is True
    return TOOL_CALL_NOT_RUN if not_run else None
