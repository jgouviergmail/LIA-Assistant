"""User-location context for the skill ReAct runner (ADR-137 follow-up).

The defect this closes: the skill sub-agent ran with no notion of where the
user is — the skill-bypass plan is empty (no ``get_current_location_tool``
step, hence no ``<collected_data>``) and the runner's four skill tools cannot
resolve a position. Asked "montre-moi où je suis", the model improvised and
passed the literal strings "ma position" then "France" as Google Maps search
queries (production run ``77ae2a29``, 2026-07-21).

Resolution goes through :func:`resolve_location` — the same chokepoint every
location-aware tool uses (browser geolocation, then the opt-in fresh
last-known position, then home address, with phrase-driven priorities;
ADR-219) — never a parallel ad-hoc read of the browser context. The rendered
value is deliberately language-free (coordinates, optionally suffixed with
the ``(last_known <timestamp>)`` age marker, or the ``unknown`` sentinel):
all wording around it lives in the versioned prompt file
``skill_react_agent_prompt`` (rule #16 — no LLM scaffolding in Python).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

logger = get_logger(__name__)

#: Sentinel rendered when no location source is available. Part of the prompt
#: contract: ``skill_react_agent_prompt.txt`` documents this literal verbatim
#: (pinned by ``test_skill_location_context.py``) — change both together.
LOCATION_UNKNOWN_VALUE = "unknown"


def _noop_stream_writer(_: object) -> None:
    """Satisfy the ``ToolRuntime`` contract outside a streaming tool call."""


async def resolve_user_location_for_prompt(
    config: RunnableConfig,
    user_message: str,
    language: str,
) -> str:
    """Resolve the user's position into a prompt-ready, language-free value.

    Args:
        config: The graph's RunnableConfig. ``configurable`` carries
            ``__browser_context`` (precise, user-consented geolocation) and
            ``user_id`` (home-address lookup) — both consumed downstream by
            :func:`resolve_location`'s source helpers.
        user_message: Latest user message, for location-phrase detection.
        language: User language for the phrase-detection tables.

    Returns:
        ``"lat,lon"`` (5 decimals, ~1 m resolution), suffixed with the saved
        address when the resolved source carries one, or
        :data:`LOCATION_UNKNOWN_VALUE` when nothing is available. The rules
        telling the model how to use (and how to NOT misuse) this value live
        in the versioned prompt, next to the other context lines.
    """
    from langchain.tools import ToolRuntime

    from src.domains.agents.context.runtime_context import (
        LiaRuntimeContext,
        runtime_context_if_running,
    )
    from src.domains.agents.tools.location_resolution import resolve_location

    try:
        # Synthetic runtime: resolve_location and its source helpers only read
        # ``runtime.config`` — there is no tool call, hence the empty state and
        # absent store (the state dict shape matches resolve_location's bound).
        runtime: ToolRuntime[LiaRuntimeContext | None, dict[Any, Any]] = ToolRuntime(
            state={},
            context=runtime_context_if_running(),
            config=config,
            stream_writer=_noop_stream_writer,
            tool_call_id=None,
            store=None,
        )
        location, _fallback = await resolve_location(runtime, user_message, language)
    except Exception as exc:
        # Degraded context beats a dead skill turn: the runner can still ask
        # the user for their position, while a raise here would kill the run.
        logger.warning(
            "skill_runner_location_resolution_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return LOCATION_UNKNOWN_VALUE

    if location is None:
        logger.info("skill_runner_location_unresolved", language=language)
        return LOCATION_UNKNOWN_VALUE

    # Coordinates (and address) are PII: they go to the prompt, never to logs.
    logger.info("skill_runner_location_resolved", source=location.source)
    value = f"{location.lat:.5f},{location.lon:.5f}"
    if location.address:
        value = f"{value} ({location.address})"
    if location.source == "last_known" and location.as_of is not None:
        # Language-free age marker, documented verbatim in the versioned
        # prompt: the model must state the position's age, never present a
        # persisted point as the live one.
        value = f"{value} (last_known {location.as_of.strftime('%Y-%m-%dT%H:%M')}Z)"
    return value
