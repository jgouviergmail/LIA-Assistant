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
    what was cut short (always) and what failed (diagnostics-gated).

    Args:
        state: The LangGraph state (completed_steps + messages are read).

    Returns:
        The formatted directive; NEVER raises — a broken diagnostics path
        must not break response synthesis.
    """
    blocks = [build_truncation_block(state)]
    blocks.append(await _diagnostics_failures_block(state))
    return "\n\n".join(block for block in blocks if block)


async def _diagnostics_failures_block(state: dict[str, Any]) -> str:
    """The typed runtime failures of the turn, or "" when the flag is off."""
    if not getattr(settings, "diagnostics_enabled", False):
        return ""
    try:
        from src.domains.agents.prompts.prompt_loader import load_prompt
        from src.domains.diagnostics.failure_context import (
            build_runtime_failures_directive,
        )

        messages: list[BaseMessage] = state.get("messages") or []
        return await build_runtime_failures_directive(
            completed_steps=state.get("completed_steps"),
            messages=messages,
            template=str(load_prompt("runtime_failures_directive")),
        )
    except Exception as exc:
        logger.debug("runtime_failures_block_failed", error=str(exc))
        return ""
