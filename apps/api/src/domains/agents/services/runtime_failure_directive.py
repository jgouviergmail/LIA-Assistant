"""Response-node adapter for the diagnostics honesty block (spec 2026-08-27).

This thin module is what keeps the domain graph acyclic (F009): it lives in
AGENTS, loads the versioned prompt with the agents loader, and delegates the
data work to ``domains.diagnostics.failure_context`` — so diagnostics never
imports agents, while agents may import diagnostics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from src.core.config import settings
from src.domains.agents.services.nothing_new import note_run_admission
from src.domains.agents.services.outcome_directive import build_requested_outcomes_block
from src.domains.agents.utils.message_filters import current_turn_responses

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

logger = structlog.get_logger(__name__)


def build_truncation_block(state: dict[str, Any]) -> str:
    """What the run could NOT finish, when it was cut short.

    Deliberately NOT gated on ``diagnostics_enabled``: telling the user that an
    investigation stopped early is answer quality, not observability. A
    self-hoster who runs without the telemetry stack still gets the truth.

    Args:
        state: The LangGraph state (``react_agent_result.truncation`` is read).

    Returns:
        The formatted directive, or "" when the run completed normally.
    """
    react_result = state.get("react_agent_result") or {}
    truncation = react_result.get("truncation") if isinstance(react_result, dict) else None
    if not isinstance(truncation, dict):
        return ""
    try:
        from src.domains.agents.prompts.prompt_loader import load_prompt

        return str(load_prompt("react_truncation_directive")).format(
            reason=truncation.get("reason", "unknown"),
            iterations=truncation.get("iterations", 0),
        )
    except Exception as exc:
        logger.debug("truncation_block_failed", error=str(exc))
        return ""


async def build_run_honesty_block(state: dict[str, Any]) -> str:
    """Everything this answer must admit about its own run.

    Two independent halves, joined here so the response node keeps ONE seam:
    what was cut short and what failed — both ALWAYS. Only the platform
    DEGRADATION paragraph waits for the diagnostics subsystem, which owns
    the advisor. Telling someone that their calendar call failed is not a
    diagnostics feature; it is the answer being honest (ADR-303).

    Args:
        state: The LangGraph state (completed_steps + messages are read).

    Returns:
        The formatted directive; NEVER raises — a broken diagnostics path
        must not break response synthesis.
    """
    truncation = build_truncation_block(state)
    failures = await _failures_block(state)
    not_run = held_not_run_block(state)
    if truncation or not_run or _turn_failed(state):
        # A routine told to notify only of something new: a run that failed
        # somewhere is never « nothing new », whatever its model declares. The
        # failures block may speak of the PLATFORM alone (a degradation): told
        # to the model, no failure of the run.
        note_run_admission()
    blocks = [truncation, build_requested_outcomes_block(state), failures, not_run]
    return "\n\n".join(block for block in blocks if block)


def _turn_failed(state: dict[str, Any]) -> bool:
    """Whether a step or a call of THIS turn failed — the count the directive states.

    Args:
        state: The LangGraph state (``completed_steps`` and ``messages`` are read).

    Returns:
        True when the turn failed somewhere, and when it cannot be told: the
        seam never raises, and doubt notifies.
    """
    try:
        from src.domains.diagnostics.failure_context import count_turn_failures

        messages: list[BaseMessage] = state.get("messages") or []
        return (
            count_turn_failures(state.get("completed_steps"), current_turn_responses(messages)) > 0
        )
    except Exception as exc:  # the seam never breaks synthesis; doubt notifies
        logger.debug("turn_failure_count_failed", error_type=type(exc).__name__)
        return True


def held_not_run_block(state: dict[str, Any]) -> str:
    """The plan's steps left unrun because an act they needed did not happen (spec D7).

    A step that waited for the person's approval runs only once every act it
    reads was confirmed AND succeeded; otherwise it never ran — and an answer
    silent about it would read as done.

    Args:
        state: The LangGraph state (``held_plan.not_run`` and the plan are read).

    Returns:
        The directive, or "" when no step was left unrun.
    """
    not_run = (state.get("held_plan") or {}).get("not_run") or {}
    if not not_run:
        return ""
    from src.domains.agents.prompts.prompt_loader import load_prompt

    tools = _tool_names_by_step(state.get("execution_plan"))
    steps = "\n".join(
        f"- {tools.get(step_id) or step_id}: {reason}" for step_id, reason in not_run.items()
    )
    return str(load_prompt("response_directive_held_not_run")).format(steps=steps)


async def _failures_block(state: dict[str, Any]) -> str:
    """The typed runtime failures of the turn, or "" when the turn was clean."""
    try:
        from src.domains.agents.prompts.prompt_loader import load_prompt
        from src.domains.diagnostics.failure_context import (
            build_runtime_failures_directive,
        )

        messages: list[BaseMessage] = state.get("messages") or []
        return await build_runtime_failures_directive(
            completed_steps=state.get("completed_steps"),
            # THIS turn's tool results: the thread's restated an earlier
            # turn's failures as the current one's.
            messages=current_turn_responses(messages),
            template=str(load_prompt("runtime_failures_directive")),
            tool_names_by_step=_tool_names_by_step(state.get("execution_plan")),
            include_degradations=bool(getattr(settings, "diagnostics_enabled", False)),
        )
    except Exception as exc:
        logger.debug("runtime_failures_block_failed", error=str(exc))
        return ""


def _tool_names_by_step(execution_plan: Any) -> dict[str, str]:
    """``step_id → tool_name`` from the plan, empty when the turn had none.

    A failure that names ``step_2`` tells the model nothing; one that names
    ``get_events_tool`` tells it which capability to speak about.

    Args:
        execution_plan: The plan the turn executed, or None.

    Returns:
        The mapping, empty for a turn with no plan (ReAct, conversation).
    """
    steps = getattr(execution_plan, "steps", None) or []
    return {
        str(getattr(step, "step_id", "")): str(getattr(step, "tool_name", "") or "")
        for step in steps
    }
