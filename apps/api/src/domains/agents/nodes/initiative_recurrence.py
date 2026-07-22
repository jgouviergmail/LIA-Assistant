"""Initiative wrapper: deterministic recurrence suggestion (P12, ADR-140).

Extracted from ``initiative_node.py`` (file-size ratchet). The graph mounts
:func:`initiative_node` from HERE — it runs the historical core
(``initiative_node._initiative_core``) untouched, then merges the
recurrence-detector suggestion into the existing
``STATE_KEY_INITIATIVE_SUGGESTION`` slot when the core produced none.
One-way dependency: this module imports the core, never the reverse.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from src.core.config import settings
from src.core.constants import STATE_KEY_INITIATIVE_SUGGESTION
from src.domains.agents.nodes.initiative_node import _extract_run_id, _initiative_core

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from src.domains.agents.models import MessagesState

logger = structlog.get_logger(__name__)


async def _resolve_recurrence_suggestion(
    state: MessagesState,
    config: RunnableConfig,
) -> str | None:
    """Deterministic recurrence check (P12, ADR-140) — no LLM involved.

    Fires only for actionable turns whose request shape accumulated hits on
    enough distinct days (see ``recurrence_ledger``). Returns the localized
    suggestion text, or None.
    """
    if not settings.recurrence_suggestion_enabled:
        return None
    from src.domains.agents.analysis.query_intelligence_helpers import get_qi_attr

    qi_intent = get_qi_attr(state, "intent", default=None)
    qi_primary = get_qi_attr(state, "primary_domain", default=None)
    if qi_intent != "action" or not qi_primary:
        return None
    user_id = config.get("configurable", {}).get("langgraph_user_id")
    if not user_id:
        return None

    from datetime import datetime
    from zoneinfo import ZoneInfo

    from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
    from src.domains.agents.services.recurrence_ledger import (
        build_signature,
        evaluate_suggestion,
    )

    try:
        user_tz = ZoneInfo(state.get("user_timezone", DEFAULT_USER_DISPLAY_TIMEZONE))
    except (KeyError, ValueError, TypeError):
        user_tz = ZoneInfo(DEFAULT_USER_DISPLAY_TIMEZONE)
    signature = build_signature(
        str(qi_primary),
        list(get_qi_attr(state, "secondary_domains", default=[]) or []),
        local_hour=datetime.now(user_tz).hour,
    )
    return await evaluate_suggestion(
        user_id,
        signature,
        language=state.get("user_language", settings.default_language),
        settings=settings,
    )


async def initiative_node(
    state: MessagesState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Initiative core + deterministic recurrence suggestion (P12).

    Thin wrapper: runs the historical initiative evaluation, then — when the
    core produced NO suggestion of its own — merges the recurrence-detector
    suggestion into the same ``STATE_KEY_INITIATIVE_SUGGESTION`` slot (the
    response node already renders that directive). Independent flags: the
    recurrence check runs even when ``initiative_enabled`` is off (the core
    then returns ``{}``), and never overrides an LLM suggestion.

    Args:
        state: Current graph state with execution results.
        config: RunnableConfig with user_id, thread_id, store, callbacks.

    Returns:
        State update dict (possibly carrying the recurrence suggestion).
    """
    state_update = await _initiative_core(state, config)

    if state_update.get(STATE_KEY_INITIATIVE_SUGGESTION):
        return state_update

    try:
        suggestion = await _resolve_recurrence_suggestion(state, config)
    except Exception as exc:  # noqa: BLE001 — advisory, never breaks the node
        logger.debug("recurrence_suggestion_failed", error=str(exc))
        return state_update

    if suggestion:
        state_update = {**state_update, STATE_KEY_INITIATIVE_SUGGESTION: suggestion}
        logger.info(
            "recurrence_suggestion_injected",
            run_id=_extract_run_id(config),
        )
    return state_update
