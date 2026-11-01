"""
Context resolution service for multi-turn conversations.

Resolves context references detected by the QueryAnalyzer LLM to actual items
via ToolContextManager, agent_results, and data_registry fallbacks.

LLM-first approach (2026-04): Reference detection is delegated to the
QueryAnalyzer LLM which sees conversation history and understands semantics
natively. Eliminates regex-based false positives and stale routing_history bugs.

This service is stateless - all request state is passed via method parameters.

Created: 2025-01
Phase: Context Resolution - Planner Reliability Improvement
Updated: 2026-04 - LLM-First Context Reference Detection
Updated: 2026-04 - Reference resolution also maintains current_item:
    an item evoked by the user (ordinal, demonstrative, pronoun) becomes the
    new focused item. Enforces the rule "current = last item manipulated,
    searched, or evoked by the user".
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, cast

import structlog
from langchain_core.runnables import RunnableConfig

from src.core.config import Settings, get_settings, settings
from src.domains.agents.constants import (
    STATE_KEY_AGENT_RESULTS,
    STATE_KEY_CURRENT_TURN_ID,
    STATE_KEY_LAST_LIST_DOMAIN,
    STATE_KEY_LAST_LIST_TURN_ID,
    TURN_TYPE_ACTION,
    TURN_TYPE_REFERENCE,
)
from src.domains.agents.context.access import get_tcm_session
from src.domains.agents.context.runtime_context import runtime_user_id_str
from src.domains.agents.context.shown_items import ordinal_list
from src.domains.agents.models import MessagesState
from src.domains.agents.services.analysis.query_analysis_schemas import REFERENCE_TYPE_DESCRIPTIVE
from src.domains.agents.services.descriptive_reference import resolve_descriptive_reference
from src.domains.agents.services.reference_fallbacks import (
    extract_all_items,
    extract_items_from_registry,
    resolved_payload,
    results_for_turn,
)
from src.domains.agents.services.reference_resolver import ResolvedContext
from src.domains.agents.utils.type_domain_mapping import TOOL_PATTERN_TO_DOMAIN_MAP
from src.infrastructure.observability.metrics_agents import (
    context_resolution_attempts_total,
    context_resolution_confidence_score,
    context_resolution_duration_seconds,
    context_resolution_turn_type_distribution_total,
)

if TYPE_CHECKING:
    from src.domains.agents.services.query_analyzer_service import ContextReferenceOutput

logger = structlog.get_logger(__name__)


# =============================================================================
# CONTEXT RESOLUTION SERVICE
# =============================================================================


class ContextResolutionService:
    """
    Resolves context for follow-up questions in multi-turn conversations.

    Uses LLM-detected context references (from QueryAnalyzer structured output)
    to identify when users reference previous results, and resolves those
    references to actual items via ToolContextManager.

    LLM-first approach (2026-04): Reference detection is delegated to the
    QueryAnalyzer LLM which sees conversation history and understands semantics
    natively. Eliminates regex-based false positives and stale routing_history bugs.

    Resolution Strategy:
        1. LLM detects reference type and domain via context_reference output
        2. If reference detected, fetch items from ToolContextManager (primary)
        3. Fallback to agent_results/data_registry if TCM empty
        4. Resolve ordinals, demonstratives, or pronouns to specific items

    Usage:
        service = get_context_resolution_service()
        resolved, turn_type = await service.resolve_context(
            query=user_message,
            state=state,
            config=config,
            run_id=run_id,
            context_reference=llm_context_reference,
        )
    """

    def __init__(
        self,
        settings: Settings | None = None,
    ):
        """
        Initialize ContextResolutionService.

        Args:
            settings: Optional settings. Uses global settings if not provided.
        """
        self.settings = settings or get_settings()

    async def resolve_context(
        self,
        query: str,
        state: MessagesState,
        config: RunnableConfig,
        run_id: str,
        *,
        context_reference: ContextReferenceOutput,
    ) -> tuple[ResolvedContext, str]:
        """Resolve context for a user query using LLM-detected references.

        Uses the context_reference from QueryAnalyzer's structured output to
        determine if the query references previous results, then resolves those
        references to actual items via ToolContextManager.

        Args:
            query: User query text (for logging only).
            state: Current conversation state.
            config: LangGraph runnable config.
            run_id: Current run ID for logging.
            context_reference: LLM-detected context reference from QueryAnalyzer.

        Returns:
            Tuple of (ResolvedContext, turn_type).
            turn_type is one of: "action", "reference"

        Example:
            >>> from src.domains.agents.services.query_analyzer_service import (
            ...     ContextReferenceOutput,
            ... )
            >>> service = get_context_resolution_service()
            >>> ref = ContextReferenceOutput(
            ...     has_reference=True,
            ...     reference_type="ordinal",
            ...     ordinal_positions=[1],
            ...     reference_domain="contact",
            ... )
            >>> resolved, turn_type = await service.resolve_context(
            ...     query="details of the first one",
            ...     state=state,
            ...     config=config,
            ...     run_id="run_123",
            ...     context_reference=ref,
            ... )
            >>> turn_type
            'reference'
            >>> len(resolved.items)
            1
        """
        start_time = time.perf_counter()

        try:
            # Check if resolution is enabled (system kill-switch)
            if not self.settings.context_reference_resolution_enabled:
                duration_seconds = (time.perf_counter() - start_time) * 1000.0 / 1000.0
                context_resolution_attempts_total.labels(turn_type="disabled").inc()
                context_resolution_turn_type_distribution_total.labels(turn_type="disabled").inc()
                context_resolution_duration_seconds.labels(turn_type="disabled").observe(
                    duration_seconds
                )
                context_resolution_confidence_score.labels(turn_type="disabled").observe(1.0)

                return (
                    ResolvedContext(
                        items=[],
                        confidence=1.0,
                        method="disabled",
                        source_turn_id=None,
                    ),
                    TURN_TYPE_ACTION,
                )

            # LLM-first: use structured context_reference from QueryAnalyzer.
            # A DESCRIBED item is resolved against what was shown (ADR-367) —
            # only when the analyzer says a shown item is designated at all.
            described = context_reference.reference_type == REFERENCE_TYPE_DESCRIPTIVE
            if context_reference.has_reference and described:
                result = resolve_descriptive_reference(context_reference, state)
                turn_type = TURN_TYPE_REFERENCE if result.items else TURN_TYPE_ACTION
                method = result.method
            elif context_reference.has_reference:
                result = await self._resolve_llm_detected_reference(
                    context_reference, state, config, run_id
                )
                turn_type = TURN_TYPE_REFERENCE
                method = "llm_detected"
            else:
                result = ResolvedContext(
                    items=[],
                    confidence=1.0,
                    method="none",
                    source_turn_id=None,
                )
                turn_type = TURN_TYPE_ACTION
                method = "none"

            # Calculate duration and log
            duration_ms = (time.perf_counter() - start_time) * 1000
            duration_seconds = duration_ms / 1000.0

            logger.info(
                "context_resolution_completed",
                run_id=run_id,
                method=method,
                turn_type=turn_type,
                confidence=result.confidence,
                items_count=len(result.items),
                source_turn_id=result.source_turn_id,
                duration_ms=round(duration_ms, 2),
                detection_query_length=len(query) if query else 0,
                llm_has_reference=context_reference.has_reference,
                llm_reference_type=context_reference.reference_type,
            )

            # Prometheus metrics
            context_resolution_attempts_total.labels(turn_type=turn_type).inc()
            context_resolution_turn_type_distribution_total.labels(turn_type=turn_type).inc()
            context_resolution_duration_seconds.labels(turn_type=turn_type).observe(
                duration_seconds
            )
            context_resolution_confidence_score.labels(turn_type=turn_type).observe(
                result.confidence
            )

            return result, turn_type

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            duration_seconds = duration_ms / 1000.0

            logger.error(
                "context_resolution_failed",
                run_id=run_id,
                error=str(e),
                error_type=type(e).__name__,
                duration_ms=round(duration_ms, 2),
            )

            context_resolution_attempts_total.labels(turn_type="error").inc()
            context_resolution_turn_type_distribution_total.labels(turn_type="error").inc()
            context_resolution_duration_seconds.labels(turn_type="error").observe(duration_seconds)
            context_resolution_confidence_score.labels(turn_type="error").observe(0.0)

            # Fallback to action turn on error
            return (
                ResolvedContext(
                    items=[],
                    confidence=0.0,
                    method="error",
                    source_turn_id=None,
                ),
                TURN_TYPE_ACTION,
            )

    async def _resolve_llm_detected_reference(
        self,
        context_reference: ContextReferenceOutput,
        state: MessagesState,
        config: RunnableConfig,
        run_id: str,
    ) -> ResolvedContext:
        """Resolve a context reference detected by the QueryAnalyzer LLM.

        LLM-first approach: the LLM provides the reference type, domain, and
        ordinal positions. This method uses existing ToolContextManager infrastructure
        to fetch actual items and resolve the reference.

        Domain source priority:
        1. context_reference.reference_domain (LLM-detected, singular)
        2. STATE_KEY_LAST_LIST_DOMAIN (fallback, plural → normalized to singular)
        Never reads routing_history — eliminates the stale-state bug.

        Item fetch priority (3 strategies, same as legacy):
        1. ToolContextManager.get_list() — primary, canonical source
        2. agent_results from last list turn — fallback if TCM empty
        3. data_registry — final fallback

        Args:
            context_reference: LLM-detected reference with type, domain, positions.
            state: Current conversation state.
            config: RunnableConfig with user_id and thread_id for Store access.
            run_id: Current run ID for logging.

        Returns:
            ResolvedContext with resolved items, confidence, and source_domain.
        """
        from src.domains.agents.utils.type_domain_mapping import (
            get_domain_from_result_key,
        )

        last_list_turn = cast(int | None, state.get(STATE_KEY_LAST_LIST_TURN_ID))

        # === 1. DOMAIN RESOLUTION (always singular) ===
        source_domain: str | None = context_reference.reference_domain or None

        if not source_domain:
            # Fallback to last_list_domain (plural from task_orchestrator)
            # Normalize plural → singular via reverse lookup
            last_list_domain = state.get(STATE_KEY_LAST_LIST_DOMAIN)
            if last_list_domain:
                source_domain = get_domain_from_result_key(str(last_list_domain)) or str(
                    last_list_domain
                )

        if not source_domain:
            logger.info(
                "llm_reference_no_domain",
                run_id=run_id,
                reference_type=context_reference.reference_type,
                reason="no_domain_from_llm_and_no_last_list_domain",
            )
            return ResolvedContext(
                items=[],
                confidence=0.0,
                method="llm_detected",
                source_turn_id=last_list_turn,
                source_domain=None,
            )

        # Translate routing domain (singular) to context domain (plural) for TCM
        context_domain = TOOL_PATTERN_TO_DOMAIN_MAP.get(source_domain, source_domain)

        logger.info(
            "llm_reference_domain_resolved",
            run_id=run_id,
            source_domain=source_domain,
            context_domain=context_domain,
            reference_type=context_reference.reference_type,
            ordinal_positions=context_reference.ordinal_positions,
        )

        # === 2. FETCH ITEMS ===
        all_items, last_list_turn = await self._list_items(
            state, config, context_domain, last_list_turn, run_id
        )

        if not all_items:
            logger.info(
                "llm_reference_no_items_found",
                run_id=run_id,
                source_domain=source_domain,
                context_domain=context_domain,
                last_list_turn_id=last_list_turn,
            )
            return ResolvedContext(
                items=[],
                confidence=0.0,
                method="llm_detected",
                source_turn_id=last_list_turn,
                source_domain=source_domain,
            )

        # === 3. RESOLVE BY TYPE ===
        resolved_items: list[Any] = []
        total_confidence = 0.0
        ref_type = context_reference.reference_type

        if ref_type == "ordinal":
            positions = context_reference.ordinal_positions
            for pos in positions:
                # Guard: 0 is invalid in 1-based (would convert to -1 = last)
                if pos == 0:
                    logger.warning(
                        "llm_ordinal_position_zero_skipped",
                        run_id=run_id,
                        reason="0 is invalid in 1-based indexing",
                    )
                    continue

                # Convert 1-based (LLM) → 0-based (Python). -1 stays -1 (last).
                index = pos - 1 if pos > 0 else pos

                if index == -1 and all_items:
                    resolved_items.append(all_items[-1])
                    total_confidence += 1.0
                elif 0 <= index < len(all_items):
                    resolved_items.append(all_items[index])
                    total_confidence += 1.0
                else:
                    logger.debug(
                        "llm_ordinal_out_of_bounds",
                        run_id=run_id,
                        position=pos,
                        index=index,
                        items_count=len(all_items),
                    )

            avg_confidence = total_confidence / len(positions) if positions else 0.0

        elif ref_type in ("demonstrative", "pronoun"):
            # Priority 1: current_item from TCM (set by detail tools)
            current_item = await self._get_current_item_from_tool_context_manager(
                config, context_domain, run_id
            )
            if current_item:
                resolved_items.append(current_item)
                avg_confidence = settings.context_current_item_confidence
                logger.info(
                    "llm_demonstrative_resolved_to_current_item",
                    run_id=run_id,
                    domain=context_domain,
                )
            elif all_items:
                # Priority 2: first item from list
                resolved_items.append(all_items[0])
                avg_confidence = settings.context_demonstrative_confidence
                logger.debug(
                    "llm_demonstrative_resolved_to_first_item",
                    run_id=run_id,
                    domain=context_domain,
                )
            else:
                avg_confidence = 0.0

        elif ref_type == "none":
            # Contradiction: has_reference=true but reference_type="none"
            logger.warning(
                "llm_reference_type_none_with_has_reference_true",
                run_id=run_id,
            )
            return ResolvedContext(
                items=[],
                confidence=0.0,
                method="llm_detected",
                source_turn_id=last_list_turn,
                source_domain=source_domain,
            )

        else:
            # Unknown reference_type: treat as demonstrative (safe fallback)
            logger.warning(
                "llm_unknown_reference_type",
                run_id=run_id,
                reference_type=ref_type,
                fallback="demonstrative",
            )
            current_item = await self._get_current_item_from_tool_context_manager(
                config, context_domain, run_id
            )
            if current_item:
                resolved_items.append(current_item)
                avg_confidence = settings.context_current_item_confidence
            elif all_items:
                resolved_items.append(all_items[0])
                avg_confidence = settings.context_demonstrative_confidence
            else:
                avg_confidence = 0.0

        logger.info(
            "llm_reference_resolved",
            run_id=run_id,
            reference_type=ref_type,
            resolved_count=len(resolved_items),
            total_items=len(all_items),
            confidence=round(avg_confidence, 2),
            source_domain=source_domain,
        )

        # Enforce the rule: current_item = last item evoked by the user.
        # A successful reference resolution is an evocation — the focus shifts.
        await self._update_current_after_resolution(
            resolved_items=resolved_items,
            state=state,
            config=config,
            context_domain=context_domain,
            run_id=run_id,
        )

        return ResolvedContext(
            items=resolved_items,
            confidence=avg_confidence,
            method="llm_detected",
            source_turn_id=last_list_turn,
            source_domain=source_domain,
        )

    async def _list_items(
        self,
        state: MessagesState,
        config: RunnableConfig,
        context_domain: str,
        last_list_turn: int | None,
        run_id: str,
    ) -> tuple[list[Any], int | None]:
        """The list an ordinal counts in, and the turn that listed it.

        What the last answers SHOWED first (ADR-367 amendment): the context list
        holds what the last LOOKUP returned, a means the answer may never have
        shown. The older strategies — the context list, the turn's agent
        results, the registry — serve a list beyond that reach.
        """
        shown_turn, shown = ordinal_list(state, context_domain)
        if shown:
            logger.info("llm_reference_items_from_shown", run_id=run_id, items=len(shown))
            items = [resolved_payload(i.item_id, dict(i.payload), i.entry) for i in shown]
            return items, shown_turn
        agent_results = cast(dict[str, Any], state.get(STATE_KEY_AGENT_RESULTS, {}))
        all_items = await self._get_items_from_tool_context_manager(config, context_domain, run_id)
        if not all_items and last_list_turn is not None:
            last_turn_results = results_for_turn(agent_results, last_list_turn)
            if last_turn_results:
                all_items = extract_all_items(last_turn_results)
        if not all_items:
            all_items = extract_items_from_registry(state, run_id, last_list_turn, agent_results)
        return all_items, last_list_turn

    async def _update_current_after_resolution(
        self,
        resolved_items: list[Any],
        state: MessagesState,
        config: RunnableConfig,
        context_domain: str,
        run_id: str,
    ) -> None:
        """Update current_item to reflect the item just evoked by the user.

        Implements the invariant: current_item always holds the last item the
        user manipulated, searched, or evoked. Reference resolution is an
        evocation, so its outcome must propagate to TCM.

        Behavior (aligned with save_list):
            - len(resolved_items) == 1 → set_current_item (unambiguous evocation)
            - len(resolved_items) > 1  → clear_current_item (ambiguous, multi-evocation)
            - len(resolved_items) == 0 → no-op (resolution failed, keep existing focus)

        Side-effect policy: failures are logged but never raise. This method
        never blocks the response path.

        Args:
            resolved_items: Items returned by the reference resolution step.
            state: Conversation state (used to extract current_turn_id for metadata).
            config: RunnableConfig carrying user_id and thread_id.
            context_domain: Plural domain key used in the TCM namespace
                (e.g. "events", "contacts"), already translated from singular.
            run_id: Run ID for logging correlation.
        """
        if not resolved_items:
            return

        try:
            session = await get_tcm_session(config)
            if session is None:
                logger.debug(
                    "current_item_update_skipped_no_session",
                    run_id=run_id,
                    domain=context_domain,
                )
                return

            turn_id = cast(int, state.get(STATE_KEY_CURRENT_TURN_ID, 0) or 0)

            if len(resolved_items) == 1:
                await session.manager.set_current_item(
                    user_id=session.user_id,
                    session_id=session.session_id,
                    domain=context_domain,
                    item=resolved_items[0],
                    set_by="auto",
                    turn_id=turn_id,
                    store=session.store,
                )
                logger.info(
                    "current_item_updated_after_resolution",
                    run_id=run_id,
                    domain=context_domain,
                    reason="single_resolved_item",
                    turn_id=turn_id,
                )
            else:
                # Multi-item evocation ("the 1st and the 3rd"): no single focus.
                await session.manager.clear_current_item(
                    user_id=session.user_id,
                    session_id=session.session_id,
                    domain=context_domain,
                    store=session.store,
                )
                logger.info(
                    "current_item_cleared_after_resolution",
                    run_id=run_id,
                    domain=context_domain,
                    reason="multiple_resolved_items",
                    count=len(resolved_items),
                )
        except Exception:
            logger.exception(
                "current_item_update_after_resolution_failed",
                run_id=run_id,
                domain=context_domain,
            )

    async def _get_items_from_tool_context_manager(
        self,
        config: RunnableConfig,
        domain: str,
        run_id: str,
    ) -> list[Any]:
        """
        Get list items from ToolContextManager.get_list().

        This is the PRIMARY source for ordinal resolution.
        The "list" key in ToolContextManager stores the last SEARCH results,
        which is NOT overwritten by detail actions.

        Args:
            config: RunnableConfig with user_id and thread_id.
            domain: Domain identifier (e.g., "contacts", "emails").
            run_id: Run ID for logging.

        Returns:
            List of items from ToolContextManager, or empty list if not found.
        """
        from src.domains.agents.context.manager import ToolContextManager
        from src.domains.agents.context.store import get_tool_context_store

        try:
            # Extract user_id and session_id from config
            configurable = config.get("configurable", {})
            user_id = runtime_user_id_str()
            session_id = configurable.get("thread_id")

            if not user_id or not session_id:
                logger.warning(
                    "get_items_from_tcm_missing_config",
                    run_id=run_id,
                    domain=domain,
                    has_user_id=bool(user_id),
                    has_session_id=bool(session_id),
                )
                return []

            # Get store instance
            store = await get_tool_context_store()

            # Get list from ToolContextManager
            manager = ToolContextManager()
            context_list = await manager.get_list(
                user_id=str(user_id),
                session_id=str(session_id),
                domain=domain,
                store=store,
            )

            if not context_list or not context_list.items:
                logger.debug(
                    "get_items_from_tcm_no_items",
                    run_id=run_id,
                    domain=domain,
                    user_id=str(user_id),
                    session_id=str(session_id),
                )
                return []

            # Return items (already indexed with 1-based "index" field)
            items = context_list.items
            logger.info(
                "get_items_from_tcm_success",
                run_id=run_id,
                domain=domain,
                items_count=len(items),
                turn_id=context_list.metadata.turn_id if context_list.metadata else None,
                tool_name=context_list.metadata.tool_name if context_list.metadata else None,
            )
            return items

        except Exception as e:
            logger.error(
                "get_items_from_tcm_failed",
                run_id=run_id,
                domain=domain,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            return []

    async def _get_current_item_from_tool_context_manager(
        self,
        config: RunnableConfig,
        domain: str,
        run_id: str,
    ) -> dict[str, Any] | None:
        """
        Get current item from ToolContextManager.get_current_item().

        The current_item is set when:
        - A get_*_details tool returns exactly 1 item (auto-set)
        - The user selects an item explicitly

        This is used for demonstrative resolution ("this appointment", "that event").
        After "details of the 2nd one", the current_item should be the 2nd event,
        so "this appointment" refers to that event, not the first in the list.

        Args:
            config: RunnableConfig with user_id and thread_id.
            domain: Domain identifier (e.g., "contacts", "events").
            run_id: Run ID for logging.

        Returns:
            Current item dict if exists, None otherwise.
        """
        from src.domains.agents.context.manager import ToolContextManager
        from src.domains.agents.context.store import get_tool_context_store

        try:
            # Extract user_id and session_id from config
            configurable = config.get("configurable", {})
            user_id = runtime_user_id_str()
            session_id = configurable.get("thread_id")

            if not user_id or not session_id:
                logger.debug(
                    "get_current_item_from_tcm_missing_config",
                    run_id=run_id,
                    domain=domain,
                    has_user_id=bool(user_id),
                    has_session_id=bool(session_id),
                )
                return None

            # Get store instance
            store = await get_tool_context_store()

            # Get current item from ToolContextManager
            manager = ToolContextManager()
            current_item = await manager.get_current_item(
                user_id=str(user_id),
                session_id=str(session_id),
                domain=domain,
                store=store,
            )

            if current_item:
                logger.debug(
                    "get_current_item_from_tcm_success",
                    run_id=run_id,
                    domain=domain,
                    item_index=current_item.get("index"),
                )
            return current_item

        except Exception as e:
            logger.error(
                "get_current_item_from_tcm_failed",
                run_id=run_id,
                domain=domain,
                error=str(e),
                error_type=type(e).__name__,
                exc_info=True,
            )
            return None


# =============================================================================
# SINGLETON PATTERN
# =============================================================================

_service_instance: ContextResolutionService | None = None


def get_context_resolution_service() -> ContextResolutionService:
    """
    Get singleton ContextResolutionService instance.

    Returns:
        Global ContextResolutionService instance.

    Usage:
        service = get_context_resolution_service()
        resolved, turn_type = await service.resolve_context(...)
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = ContextResolutionService()
    return _service_instance


def reset_context_resolution_service() -> None:
    """
    Reset singleton instance (for testing).

    Usage in tests:
        reset_context_resolution_service()
        service = get_context_resolution_service()  # Fresh instance
    """
    global _service_instance
    _service_instance = None
