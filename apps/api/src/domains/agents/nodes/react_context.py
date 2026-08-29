"""What the ReAct loop is told before it starts.

One builder per context block, each returning ``str | None`` and each
best-effort: context enriches a turn, it never gates one. ``react_setup_node``
orchestrates them and owns the injection ORDER, which is meaningful — standing
rules come first, because they govern how everything after them is used.

Split out of ``react_nodes`` (at its size cap) when memory parity was added.
The gap this module closes is the one already closed for journal directives:
a behavioural instruction that only reaches the response node can reword an
answer, never change what the loop decided to do. Memory now travels through
the SAME builder the pipeline uses (``build_psychological_profile``) — a second
implementation would drift, and drift is how the two modes came to disagree.
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from src.core.config import settings
from src.domains.agents.context.runtime_context import (
    runtime_context_if_running,
    runtime_user_id_str,
)
from src.domains.agents.middleware.memory_injection import build_psychological_profile
from src.domains.agents.models import MessagesState
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.llm.user_message_embedding import (
    get_or_compute_embedding,
    is_trivial_message,
)

logger = structlog.get_logger(__name__)


def last_user_text(state: MessagesState) -> str:
    """The most recent human message as plain text (``""`` when there is none).

    Args:
        state: Current graph state.

    Returns:
        The message text, normalized from provider block lists.
    """
    for message in reversed(state.get("messages", []) or []):
        if isinstance(message, HumanMessage):
            return coerce_content_to_text(message.content) or ""
    return ""


async def _embed_quietly(
    query: str,
    user_id: str,
    session_id: str | None,
    configurable: dict[str, Any],
) -> list[float] | None:
    """The shared embedding of the user message, or None if it cannot be had.

    Failure is not fatal here: ``build_psychological_profile`` falls back to the
    user's recent memories when it gets no vector, which is a worse search but
    still the user's memory. Aborting the profile instead would make the loop
    LESS memory-aware than the pipeline on exactly the days it matters.

    Args:
        query: The user message to embed.
        user_id: Owner, for cost attribution.
        session_id: Thread id, for cost attribution.
        configurable: The run's configurable block.

    Returns:
        The vector, or None.
    """
    from src.infrastructure.llm.embedding_context import (
        clear_embedding_context,
        set_embedding_context,
    )

    set_embedding_context(
        user_id=user_id,
        session_id=session_id or "unknown",
        run_id=configurable.get("run_id") or "",
    )
    try:
        return await get_or_compute_embedding(
            message=query,
            user_id=user_id,
            session_id=session_id,
            is_conversational=True,
        )
    except Exception as exc:
        logger.warning("react_memory_embedding_failed", error=str(exc))
        return None
    finally:
        clear_embedding_context()


async def build_memory_profile_block(
    state: MessagesState,
    config: RunnableConfig,
) -> str | None:
    """The user's psychological profile — the same one the pipeline injects.

    Parity is the whole point: same builder, same settings, same triviality
    gate, same user preference. What differs is WHERE it lands — inside the
    reasoning loop, where the decision to act is taken, instead of only in the
    final synthesis, where the answer is merely worded.

    The embedding comes from the shared get-or-compute cache, so the response
    node's later call reuses it rather than paying a second time.

    Args:
        state: Current graph state.
        config: RunnableConfig carrying the user context.

    Returns:
        The profile block, or None when memory is off, unavailable or not worth
        searching for this message.
    """
    configurable = config.get("configurable", {}) or {}
    _ctx = runtime_context_if_running()
    if not (_ctx.memory_enabled if _ctx is not None else True):
        return None

    user_id = runtime_user_id_str() or ""
    query = last_user_text(state)
    if not user_id or not query:
        return None

    session_id = configurable.get("thread_id")
    # Triviality skips the EMBEDDING, never the profile — exactly the pipeline's
    # gating. A standing rule must apply to "ok" too; without a vector the
    # builder falls back to the user's recent memories, which is the right
    # degradation and the one the other mode already gets.
    embedding: list[float] | None = None
    if not is_trivial_message(query):
        embedding = await _embed_quietly(query, user_id, session_id, configurable)

    try:
        profile, _emotional_state, _debug = await build_psychological_profile(
            user_id=user_id,
            query=query,
            query_embedding=embedding,
            limit=settings.memory_max_results,
            min_score=settings.memory_min_search_score,
            session_id=session_id,
            conversation_id=session_id,
        )
    except Exception as exc:  # pragma: no cover — best-effort, never gates a turn
        logger.warning("react_memory_profile_failed", error=str(exc))
        return None

    if not profile or not profile.strip():
        return None
    return profile


def build_reference_resolution_block(state: MessagesState, intelligence: Any) -> str | None:
    """Pre-resolved references ("mon frère" = "Marc Lemoine"), when any.

    Args:
        state: Current graph state.
        intelligence: QueryIntelligence for this turn, when available.

    Returns:
        The block, or None when nothing was resolved.
    """
    resolved = state.get("resolved_references") or (
        intelligence.resolved_references if intelligence else None
    )
    if not resolved:
        return None
    lines = [f'- "{key}" = {value}' for key, value in resolved.items()]
    return "<MemoryContext>\nReference resolution:\n" + "\n".join(lines) + "\n</MemoryContext>"


async def build_user_model_block(config: RunnableConfig) -> str | None:
    """User-model portrait — ambient diffusion (ADR-079).

    Brief format (~60 tokens) injected once at setup so the loop carries the
    same posture as the pipeline mode.

    Args:
        config: RunnableConfig carrying the user context.

    Returns:
        The portrait block, or None.
    """
    if not getattr(settings, "journals_enabled", False):
        return None
    try:
        config.get("configurable", {}) or {}
        _ctx = runtime_context_if_running()
        if not (_ctx.journals_enabled if _ctx is not None else False):
            return None
        user_id = runtime_user_id_str() or ""
        if not user_id:
            return None
        from src.domains.journals.portrait_builder import build_journal_user_model_block

        return await build_journal_user_model_block(user_id=user_id, format="brief", flow="react")
    except Exception as exc:  # pragma: no cover — best-effort
        logger.warning("react_user_model_block_failed", error=str(exc))
        return None


async def build_journal_directives_block(
    state: MessagesState,
    config: RunnableConfig,
) -> str | None:
    """Operational journal directives (L1/L2) — the cross-mode gap, closed.

    A bounded set injected ONCE at setup (count cap, no truncation) so the loop
    is guided like the pipeline planner. L0/L3 are excluded by default inside
    ``build_journal_context``. Deferred self-evaluation stays anchored to the
    response node and is deliberately not duplicated here.

    Args:
        state: Current graph state.
        config: RunnableConfig carrying the user context.

    Returns:
        The directives block, or None.
    """
    if not getattr(settings, "journals_enabled", False):
        return None
    try:
        configurable = config.get("configurable", {}) or {}
        user_id = runtime_user_id_str() or ""
        max_directives = settings.journal_react_context_max_entries
        query = last_user_text(state)
        _ctx = runtime_context_if_running()
        if not ((_ctx.journals_enabled if _ctx is not None else False) and user_id):
            return None
        if max_directives <= 0 or not query:
            return None

        from src.domains.journals.context_builder import build_journal_context
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as journal_db:
            # B-08 decision (2026-08-19): the journal ids are deliberately
            # discarded — the response-flow injection (same turn) is the
            # instance evaluated by the T→T+1 loop; this in-loop copy only
            # steers the ReAct reasoning.
            directives_block, _debug, _ids = await build_journal_context(
                user_id=user_id,
                query=query,
                db=journal_db,
                session_id=configurable.get("thread_id"),
                max_results_override=max_directives,
                truncate_to_budget=False,
            )
        return directives_block or None
    except Exception as exc:  # pragma: no cover — best-effort
        logger.warning("react_journal_directives_failed", error=str(exc))
        return None


def build_skills_catalog_block(config: RunnableConfig) -> str | None:
    """Active skills catalogue (L1), same filtered set as the pipeline planner.

    Args:
        config: RunnableConfig carrying the user context.

    Returns:
        The catalogue block, or None.
    """
    if not getattr(settings, "skills_enabled", False):
        return None
    from src.core.context import active_skills_ctx
    from src.domains.skills.injection import build_skills_catalog

    config.get("configurable", {}) or {}
    catalog = build_skills_catalog(
        user_id=runtime_user_id_str() or "",
        active_skills=active_skills_ctx.get(),
    )
    if not catalog:
        return None
    return f"<AvailableSkills>\n{catalog}\n</AvailableSkills>"


async def build_degradations_block() -> str | None:
    """Currently degraded capabilities (ADR-247, pillar 7).

    Lets the agent route around a KNOWN outage instead of discovering it by
    timeout. Empty on a healthy platform (zero tokens), fail-open by
    construction — the advisor never raises.

    Returns:
        The degradations block, or None on a healthy platform.
    """
    from src.domains.diagnostics.advisor import (
        format_degradations_block,
        get_active_degradations,
    )

    return format_degradations_block(await get_active_degradations()) or None
