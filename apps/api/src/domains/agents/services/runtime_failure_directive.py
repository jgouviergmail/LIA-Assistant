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


async def build_runtime_failures_block(state: dict[str, Any]) -> str:
    """The honesty block for one run, or "" (flag off / clean turn / failure).

    Args:
        state: The LangGraph state (completed_steps + messages are read).

    Returns:
        The formatted directive; NEVER raises — a broken diagnostics path
        must not break response synthesis.
    """
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
