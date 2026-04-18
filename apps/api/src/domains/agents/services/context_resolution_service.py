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
from src.core.field_names import FIELD_USER_ID
from src.domains.agents.constants import (
    STATE_KEY_AGENT_RESULTS,
    STATE_KEY_CURRENT_TURN_ID,
    STATE_KEY_LAST_LIST_DOMAIN,
    STATE_KEY_LAST_LIST_TURN_ID,
    TURN_TYPE_ACTION,
    TURN_TYPE_REFERENCE,
)
from src.domains.agents.context.access import get_tcm_session
from src.domains.agents.models import MessagesState
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
            ...     query="detail du premier",
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

            # LLM-first: use structured context_reference from QueryAnalyzer
            if context_reference.has_reference:
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
                detection_query=query[:80] if query else None,
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
        agent_results = cast(dict[str, Any], state.get(STATE_KEY_AGENT_RESULTS, {}))

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

        # === 2. FETCH ITEMS (3 strategies) ===
        all_items: list[Any] = []

        # Strategy 1: ToolContextManager (primary)
        all_items = await self._get_items_from_tool_context_manager(config, context_domain, run_id)

        # Strategy 2: agent_results from last list turn
        if not all_items and last_list_turn is not None:
            last_turn_results = self._get_results_for_turn(agent_results, last_list_turn)
            if last_turn_results:
                all_items = self._extract_all_items(last_turn_results)

        # Strategy 3: data_registry (final fallback)
        if not all_items:
            all_items = self._extract_items_from_registry(
                state, run_id, last_list_turn, agent_results
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
                # Multi-item evocation ("le 1er et le 3e"): no single focus.
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

    def _get_results_for_turn(
        self,
        agent_results: dict[str, Any],
        turn_id: int,
    ) -> dict[str, Any]:
        """
        Filter agent results for a specific turn.

        Args:
            agent_results: All agent results (keyed by "turn_id:agent_name").
            turn_id: Turn ID to filter by.

        Returns:
            Dict of agent_name → result for the specified turn.
        """
        results: dict[str, Any] = {}
        prefix = f"{turn_id}:"

        for key, value in agent_results.items():
            if key.startswith(prefix):
                agent_name = key[len(prefix) :]
                results[agent_name] = value

        return results

    def _extract_all_items(self, agent_results: dict[str, Any]) -> list[Any]:
        """
        Extract all list items from agent results.

        Looks for common list fields in results (emails, contacts, events, etc.)
        and aggregates them into a single list.

        BugFix 2025-12-19: Also extract from registry_updates for registry-mode tools.

        Args:
            agent_results: Dict of agent_name → result.

        Returns:
            Flattened list of all items from all agents.
        """
        from src.domains.agents.data_registry.models import RegistryItem

        all_items: list[Any] = []

        # Common list field names across domains
        # NOTE: Order matters - more specific fields first, generic fields last
        list_fields = [
            "emails",
            "contacts",
            "events",
            "files",
            "tasks",
            "places",  # Google Places search/nearby results
            "items",
            "results",
            "list",
        ]

        for _agent_name, result in agent_results.items():
            if isinstance(result, dict):
                # BugFix 2025-12-19: Check registry_updates FIRST for registry-mode tools
                # Registry-mode tools store data in registry_updates, not in traditional fields
                registry_updates = result.get("registry_updates", {})
                if registry_updates and isinstance(registry_updates, dict):
                    for _item_id, reg_item in registry_updates.items():
                        if isinstance(reg_item, RegistryItem):
                            # Enrich with metadata for domain detection
                            payload = dict(reg_item.payload)
                            payload["_registry_id"] = _item_id
                            payload["_item_type"] = reg_item.type.value
                            all_items.append(payload)
                        elif isinstance(reg_item, dict):
                            raw_payload = reg_item.get("payload", reg_item)
                            if isinstance(raw_payload, dict):
                                # Enrich with metadata for domain detection
                                payload = dict(raw_payload)
                                payload["_registry_id"] = _item_id
                                # Try to get type from dict if available
                                if "type" in reg_item:
                                    payload["_item_type"] = reg_item["type"]
                                all_items.append(payload)
                    if all_items:
                        logger.info(
                            "extract_all_items_from_registry_updates",
                            agent_name=_agent_name,
                            items_added=len(registry_updates),
                        )
                        continue  # Skip traditional field extraction

                # Check if result has "data" field (standard agent result structure)
                # Structure: {"agent_name": ..., "status": ..., "data": {"emails": [...]}}
                data_container = result.get("data", result)
                if isinstance(data_container, dict):
                    # Look for list fields in data container
                    found_field = None
                    for field in list_fields:
                        if field in data_container and isinstance(data_container[field], list):
                            all_items.extend(data_container[field])
                            found_field = field
                            break
                    if found_field:
                        logger.debug(
                            "extract_all_items_found_field",
                            agent_name=_agent_name,
                            field=found_field,
                            items_added=len(data_container[found_field]),
                        )
                    else:
                        # No known list field found - check for any list value
                        if result.get("status") == "success":
                            for key, value in data_container.items():
                                if isinstance(value, list) and key not in [
                                    "errors",
                                    "warnings",
                                ]:
                                    all_items.extend(value)
                                    logger.debug(
                                        "extract_all_items_fallback_list",
                                        agent_name=_agent_name,
                                        key=key,
                                        items_added=len(value),
                                    )
                                    break
                        else:
                            logger.debug(
                                "extract_all_items_no_match",
                                agent_name=_agent_name,
                                data_keys=list(data_container.keys())[:5],
                                result_status=result.get("status"),
                            )
            elif isinstance(result, list):
                all_items.extend(result)
                logger.debug(
                    "extract_all_items_raw_list",
                    agent_name=_agent_name,
                    items_added=len(result),
                )

        if not all_items:
            logger.debug(
                "extract_all_items_empty",
                agent_count=len(agent_results),
                agent_names=list(agent_results.keys()),
            )

        # Sort items by index field to preserve original order for ordinal resolution
        # (e.g., "the second one" should get the item with index=2)
        # Items without index field are placed at the end
        all_items.sort(key=lambda x: x.get("index", float("inf")))

        return all_items

    def _extract_items_from_registry(
        self,
        state: MessagesState,
        run_id: str,
        last_action_turn: int | None = None,
        agent_results: dict[str, Any] | None = None,
    ) -> list[Any]:
        """
        Extract items from data_registry for reference resolution.

        CRITICAL FIX 2025-12-19: Multi-level filtering strategy to prevent cross-domain
        contamination (e.g., returning contacts when user asked for "le deuxième email").

        Filtering Priority (stops at first successful filter):
        1. registry_updates from agent_results for last_action_turn
        2. turn_id in RegistryItem.meta (if populated)
        3. Domain-based filtering using detected domain from last action
        4. SAFE FALLBACK: Return empty list (never return ALL items)

        Args:
            state: Current conversation state with registry.
            run_id: Current run ID for logging.
            last_action_turn: Turn ID to filter items by.
            agent_results: Agent results to extract registry_updates from.

        Returns:
            List of item payloads from the registry, filtered to prevent cross-domain issues.
        """
        from src.domains.agents.data_registry.models import RegistryItem

        registry = state.get("registry", {})
        if not registry:
            logger.debug("no_registry_in_state", run_id=run_id)
            return []

        # =========================================================================
        # STRATEGY 1: Filter by registry_updates from agent_results
        # =========================================================================
        target_item_ids: set[str] | None = None
        filter_method = "none"

        if last_action_turn is not None and agent_results:
            target_item_ids = set()
            prefix = f"{last_action_turn}:"
            for key, result in agent_results.items():
                if key.startswith(prefix):
                    updates = {}
                    if isinstance(result, dict):
                        updates = result.get("registry_updates", {})
                    elif hasattr(result, "registry_updates"):
                        updates = getattr(result, "registry_updates", {})
                    if updates:
                        target_item_ids.update(updates.keys())

            if target_item_ids:
                filter_method = "registry_updates"
                logger.info(
                    "registry_extraction_filtered_by_registry_updates",
                    run_id=run_id,
                    turn_id=last_action_turn,
                    total_registry_count=len(registry),
                    filtered_count=len(target_item_ids),
                    filtered_ids=list(target_item_ids)[:10],
                )
            else:
                target_item_ids = None

        # =========================================================================
        # STRATEGY 2: Filter by turn_id in RegistryItem.meta
        # =========================================================================
        if target_item_ids is None and last_action_turn is not None:
            target_item_ids = set()
            for item_id, item in registry.items():
                if isinstance(item, RegistryItem):
                    if item.meta.turn_id == last_action_turn:
                        target_item_ids.add(item_id)

            if target_item_ids:
                filter_method = "turn_id_meta"
                logger.info(
                    "registry_extraction_filtered_by_turn_id_meta",
                    run_id=run_id,
                    turn_id=last_action_turn,
                    filtered_count=len(target_item_ids),
                )
            else:
                target_item_ids = None

        # =========================================================================
        # STRATEGY 3: Filter by domain from last action turn
        # =========================================================================
        if target_item_ids is None and last_action_turn is not None and agent_results:
            # Detect domain from agent_results for last action turn
            detected_domain = self._detect_domain_from_agent_results(
                agent_results, last_action_turn, run_id
            )

            if detected_domain:
                target_item_ids = set()
                for item_id, item in registry.items():
                    if isinstance(item, RegistryItem):
                        # Match by meta.domain or by item type prefix
                        item_domain = item.meta.domain
                        if item_domain is None:
                            # Fallback: derive domain from item type
                            item_domain = self._derive_domain_from_type(item.type.value)

                        if item_domain == detected_domain:
                            target_item_ids.add(item_id)

                if target_item_ids:
                    filter_method = "domain"
                    logger.info(
                        "registry_extraction_filtered_by_domain",
                        run_id=run_id,
                        detected_domain=detected_domain,
                        turn_id=last_action_turn,
                        filtered_count=len(target_item_ids),
                    )
                else:
                    target_item_ids = None

        # =========================================================================
        # STRATEGY 4: SAFE FALLBACK - Return empty rather than ALL items
        # =========================================================================
        if target_item_ids is None:
            logger.warning(
                "registry_extraction_no_valid_filter",
                run_id=run_id,
                turn_id=last_action_turn,
                total_registry_count=len(registry),
                reason="All filtering strategies failed - returning empty to prevent cross-domain contamination",
            )
            return []

        # =========================================================================
        # Extract payloads from filtered RegistryItems
        # =========================================================================
        items: list[Any] = []
        for item_id, item in registry.items():
            if item_id not in target_item_ids:
                continue

            if isinstance(item, RegistryItem):
                payload = dict(item.payload)
                payload["_registry_id"] = item_id
                payload["_item_type"] = item.type.value
                items.append(payload)
            elif isinstance(item, dict):
                payload = item.get("payload", item)
                if isinstance(payload, dict):
                    payload = dict(payload)
                    payload["_registry_id"] = item_id
                items.append(payload)
            else:
                logger.warning(
                    "registry_item_unexpected_type",
                    run_id=run_id,
                    item_id=item_id,
                    item_type=type(item).__name__,
                )

        if items:
            # Sort items by index field to preserve original order for ordinal resolution
            # (e.g., "the second one" should get the item with index=2)
            # Items without index field are placed at the end
            items.sort(key=lambda x: x.get("index", float("inf")))

            logger.info(
                "items_extracted_from_registry",
                run_id=run_id,
                items_count=len(items),
                filter_method=filter_method,
                turn_id=last_action_turn,
                item_types=[i.get("_item_type", "unknown") for i in items[:5]],
            )

        return items

    def _detect_domain_from_agent_results(
        self,
        agent_results: dict[str, Any],
        turn_id: int,
        run_id: str,
    ) -> str | None:
        """
        Detect domain from agent_results for a specific turn.

        Looks at the result structure to determine which domain the last action was for.
        This is used as a fallback when registry_updates is not available.

        Args:
            agent_results: All agent results.
            turn_id: Turn ID to look for.
            run_id: Run ID for logging.

        Returns:
            Domain name (e.g., "emails", "contacts") or None if not detected.
        """
        prefix = f"{turn_id}:"
        for key, result in agent_results.items():
            if not key.startswith(prefix):
                continue

            if not isinstance(result, dict):
                continue

            # Check for domain indicators in result structure
            # Priority: explicit 'domain' field > data keys > tool_name
            if "domain" in result:
                return str(result["domain"])

            # Check data keys
            data = result.get("data", result)
            if isinstance(data, dict):
                domain_keys = {
                    "emails": "emails",
                    "contacts": "contacts",
                    "events": "events",
                    "files": "drive",
                    "tasks": "tasks",
                    "places": "places",
                    "weather": "weather",
                    "forecasts": "weather",
                    "articles": "wikipedia",
                    "results": "perplexity",
                }
                for key_name, domain in domain_keys.items():
                    if key_name in data:
                        logger.debug(
                            "domain_detected_from_data_keys",
                            run_id=run_id,
                            turn_id=turn_id,
                            detected_key=key_name,
                            domain=domain,
                        )
                        return domain

            # Check tool_name - use centralized mapping from type_domain_mapping.py
            tool_name = result.get("tool_name", "")
            if tool_name:
                from src.domains.agents.utils.type_domain_mapping import (
                    get_domain_from_tool_name,
                )

                domain = get_domain_from_tool_name(tool_name)  # type: ignore
                if domain:
                    logger.debug(
                        "domain_detected_from_tool_name",
                        run_id=run_id,
                        turn_id=turn_id,
                        tool_name=tool_name,
                        domain=domain,
                    )
                    return domain

        return None

    def _derive_domain_from_type(self, item_type: str) -> str | None:
        """
        Derive result key (pluriel) from RegistryItemType value.

        Uses centralized TYPE_TO_DOMAIN_MAP from type_domain_mapping.py.
        Returns the pluriel form to match meta.domain convention.

        Args:
            item_type: Item type string (e.g., "EMAIL", "CONTACT").

        Returns:
            Result key (e.g., "emails", "contacts") or None.
        """
        from src.domains.agents.utils.type_domain_mapping import get_result_key_from_type

        return get_result_key_from_type(item_type)

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
            user_id = configurable.get(FIELD_USER_ID)
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

        This is used for demonstrative resolution ("ce rdv", "this event").
        After "detail du 2ème", the current_item should be the 2nd event,
        so "ce rdv" refers to that event, not the first in the list.

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
            user_id = configurable.get(FIELD_USER_ID)
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
