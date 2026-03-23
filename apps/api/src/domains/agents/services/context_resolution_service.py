"""
Context resolution service for multi-turn conversations.

Resolves references to previous agent results using:
1. Explicit reference resolution (ordinals, demonstratives)
2. Active context from last action turn
3. Turn-based fallback

Integrates with existing ToolContextManager and ContextTypeRegistry.
This service is stateless - all request state is passed via method parameters.

Created: 2025-01
Phase: Context Resolution - Planner Reliability Improvement
"""

import time
from typing import Any, cast

import structlog
from langchain_core.runnables import RunnableConfig

from src.core.config import Settings, get_settings, settings
from src.core.field_names import FIELD_USER_ID
from src.domains.agents.constants import (
    STATE_KEY_AGENT_RESULTS,
    STATE_KEY_CURRENT_TURN_ID,
    STATE_KEY_LAST_LIST_DOMAIN,
    STATE_KEY_LAST_LIST_TURN_ID,
    STATE_KEY_ROUTING_HISTORY,
    TURN_TYPE_ACTION,
    TURN_TYPE_CONVERSATIONAL,
    TURN_TYPE_REFERENCE,
)
from src.domains.agents.models import MessagesState
from src.domains.agents.services.reference_resolver import (
    ExtractedReferences,
    ResolvedContext,
    get_reference_resolver,
)
from src.domains.agents.utils.type_domain_mapping import TOOL_PATTERN_TO_DOMAIN_MAP
from src.infrastructure.observability.metrics_agents import (
    context_resolution_attempts_total,
    context_resolution_confidence_score,
    context_resolution_duration_seconds,
    context_resolution_turn_type_distribution_total,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# CONTEXT RESOLUTION SERVICE
# =============================================================================


class ContextResolutionService:
    """
    Resolves context for follow-up questions in multi-turn conversations.

    Uses existing ToolContextManager for context storage and adds a reference
    resolution layer on top. Domain-agnostic - works with any agent results.

    Resolution Strategy:
    1. Check for explicit linguistic references ("le deuxième", "celui-ci")
    2. If found, resolve to items from last_action_turn_id
    3. If not found, classify as action or conversational turn

    Usage:
        service = get_context_resolution_service()
        resolved, turn_type = await service.resolve_context(
            query=user_message,
            state=state,
            config=config,
            run_id=run_id,
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
        self.reference_resolver = get_reference_resolver()

    async def resolve_context(
        self,
        query: str,
        state: MessagesState,
        config: RunnableConfig,
        run_id: str,
        english_query: str | None = None,
    ) -> tuple[ResolvedContext, str]:
        """
        Resolve context for a user query.

        Determines if the query references previous results and resolves
        those references to actual items. Also classifies the turn type.

        Args:
            query: User query text (original language).
            state: Current conversation state.
            config: LangGraph runnable config.
            run_id: Current run ID for logging.
            english_query: Optional translated English query from Semantic Pivot.
                          If provided, used for reference detection with English patterns only.
                          This avoids maintaining regex patterns for all supported languages.

        Returns:
            Tuple of (ResolvedContext, turn_type).
            turn_type is one of: "action", "reference", "conversational"

        Example:
            >>> service = get_context_resolution_service()
            >>> resolved, turn_type = await service.resolve_context(
            ...     query="detail de la premiere",
            ...     state=state,
            ...     config=config,
            ...     run_id="run_123",
            ...     english_query="details of the first one",
            ... )
            >>> turn_type
            'reference'
            >>> len(resolved.items)
            1
        """
        start_time = time.perf_counter()

        try:
            # Check if resolution is enabled
            if not self.settings.context_reference_resolution_enabled:
                # PHASE 1.2 - Context resolution metrics instrumentation (disabled case)
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

            # Extract references from query
            # SEMANTIC PIVOT FIX (2025-12-25): Use english_query if available for reference detection.
            # This allows using English-only patterns instead of maintaining patterns for all languages.
            # Example: "detail de la premiere" → english_query="details of the first one" → matches "first"
            detection_query = english_query if english_query else query
            references = self.reference_resolver.extract_references(
                detection_query, english_only=bool(english_query)
            )

            if references.has_explicit():
                # Has explicit references → resolve them
                result = await self._resolve_explicit_references(references, state, config, run_id)
                turn_type = TURN_TYPE_REFERENCE
                method = "explicit"
            else:
                # No explicit references → default to action turn
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
                # SEMANTIC PIVOT: Log which query was used for reference detection
                detection_query=detection_query[:80] if detection_query else None,
                used_english_pivot=bool(english_query),
            )

            # PHASE 1.2 - Context resolution metrics instrumentation
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

            # PHASE 1.2 - Context resolution metrics instrumentation (error case)
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

    async def _resolve_explicit_references(
        self,
        references: ExtractedReferences,
        state: MessagesState,
        config: RunnableConfig,
        run_id: str,
    ) -> ResolvedContext:
        """
        Resolve explicit references to items from previous results.

        REFACTORED 2025-01: Uses ToolContextManager.get_list() as PRIMARY and ONLY source.
        This is the canonical approach because:
        - The "list" key stores the LAST SEARCH results (not overwritten by detail actions)
        - Works consistently across ALL domains (contacts, emails, calendar, etc.)
        - Decoupled from last_action_turn_id which gets overwritten by ALL actions

        Resolution Strategy:
        1. Detect domain: routing_history[-1].domains || last_list_domain
        2. Get items: ToolContextManager.get_list(domain) - canonical source
        3. Fallback to last_list_turn_id extraction (if TCM empty, e.g., Redis down)

        IMPORTANT: We use last_list_turn_id (not last_action_turn_id) for fallback.
        last_list_turn_id is ONLY updated when LIST tools execute (search_*, list_*).
        last_action_turn_id is overwritten by ALL actions including details.

        Args:
            references: Extracted references from query.
            state: Current conversation state.
            config: RunnableConfig with user_id, thread_id for Store access.
            run_id: Current run ID for logging.

        Returns:
            ResolvedContext with resolved items.
        """
        # Get last LIST turn (NOT last action turn - that's the bug we fixed!)
        last_list_turn = cast(int | None, state.get(STATE_KEY_LAST_LIST_TURN_ID))
        agent_results = cast(dict[str, Any], state.get(STATE_KEY_AGENT_RESULTS, {}))

        # Detect domain for ordinal resolution
        source_domain = self._detect_domain_for_ordinal_resolution(state, run_id)

        logger.info(
            "context_resolution_state_debug",
            run_id=run_id,
            last_list_turn_id=last_list_turn,
            source_domain=source_domain,
            agent_results_keys=list(agent_results.keys()) if agent_results else [],
            current_turn_id=state.get(STATE_KEY_CURRENT_TURN_ID),
        )

        # =========================================================================
        # STRATEGY 1: Use ToolContextManager.get_list() as PRIMARY source
        # This is the CANONICAL approach - stores last search results per domain
        # =========================================================================
        all_items: list[Any] = []
        resolution_method = "explicit"

        if source_domain:
            # CRITICAL: Translate routing domain to context domain
            # Router uses "calendar" but TCM stores under "events"
            # See TOOL_PATTERN_TO_DOMAIN_MAP for full mapping
            context_domain = TOOL_PATTERN_TO_DOMAIN_MAP.get(source_domain, source_domain)
            if context_domain != source_domain:
                logger.debug(
                    "routing_to_context_domain_translation",
                    run_id=run_id,
                    routing_domain=source_domain,
                    context_domain=context_domain,
                )

            # Try to get items from ToolContextManager
            context_items = await self._get_items_from_tool_context_manager(
                config, context_domain, run_id
            )
            if context_items:
                all_items = context_items
                resolution_method = "tool_context_manager"
                logger.info(
                    "context_resolution_from_tool_context_manager",
                    run_id=run_id,
                    routing_domain=source_domain,
                    context_domain=context_domain,
                    items_count=len(all_items),
                )

        # =========================================================================
        # STRATEGY 2: Fallback to last_list_turn extraction (if TCM empty)
        # Uses last_list_turn_id (NOT last_action_turn_id) to avoid the bug
        # =========================================================================
        if not all_items and last_list_turn is not None:
            # Get agent results from last LIST turn (not last action)
            last_turn_results = self._get_results_for_turn(agent_results, last_list_turn)

            if last_turn_results:
                # Extract all items from agent results
                all_items = self._extract_all_items(last_turn_results)
                if all_items:
                    resolution_method = "agent_results_list_turn"
                    logger.info(
                        "context_resolution_from_agent_results",
                        run_id=run_id,
                        turn_id=last_list_turn,
                        items_count=len(all_items),
                    )

            # Fallback to data_registry if agent_results only have summaries
            if not all_items:
                all_items = self._extract_items_from_registry(
                    state, run_id, last_list_turn, agent_results
                )
                if all_items:
                    resolution_method = "data_registry"
                    logger.info(
                        "context_resolution_from_registry",
                        run_id=run_id,
                        turn_id=last_list_turn,
                        items_count=len(all_items),
                    )

        # No items found - return empty result
        if not all_items:
            logger.info(
                "context_resolution_no_items_found",
                run_id=run_id,
                source_domain=source_domain,
                last_list_turn_id=last_list_turn,
                resolution_method=resolution_method,
            )
            return ResolvedContext(
                items=[],
                confidence=0.0,
                method="explicit",
                source_turn_id=last_list_turn,
                source_domain=source_domain,
            )

        # Debug: Log available items before resolution
        logger.debug(
            "ordinal_resolution_start",
            run_id=run_id,
            all_items_count=len(all_items),
            ordinal_refs=[r.index for r in references.get_ordinals()],
            demonstrative_refs=len(references.get_demonstratives()),
        )

        # Resolve ordinal references
        resolved_items: list[Any] = []
        total_confidence = 0.0

        for ref in references.get_ordinals():
            if ref.index is not None:
                item, confidence = self.reference_resolver.resolve_ordinal_to_item(
                    ref.index, all_items
                )
                if item is not None:
                    resolved_items.append(item)
                    total_confidence += confidence
                else:
                    # Log failed resolution for debugging
                    logger.debug(
                        "ordinal_resolution_failed",
                        run_id=run_id,
                        ordinal_index=ref.index,
                        all_items_count=len(all_items),
                        reason="index_out_of_bounds" if ref.index >= len(all_items) else "unknown",
                    )

        # Resolve demonstrative references
        # PRIORITY: current_item > list[0]
        # "ce rdv", "this event" refers to the CURRENT item (after "detail du 2e"),
        # not necessarily the first item in the list.
        for _ref in references.get_demonstratives():
            # Try current_item first (set by get_*_details tools)
            if source_domain:
                context_domain = TOOL_PATTERN_TO_DOMAIN_MAP.get(source_domain, source_domain)
                current_item = await self._get_current_item_from_tool_context_manager(
                    config, context_domain, run_id
                )
                if current_item:
                    resolved_items.append(current_item)
                    total_confidence += settings.context_current_item_confidence
                    logger.info(
                        "demonstrative_resolved_to_current_item",
                        run_id=run_id,
                        domain=context_domain,
                        item_index=current_item.get("index"),
                        reason="current_item_exists",
                    )
                    continue  # Skip fallback to list[0]

            # Fallback: use first item from list
            if all_items:
                resolved_items.append(all_items[0])
                total_confidence += settings.context_demonstrative_confidence
                logger.debug(
                    "demonstrative_resolved_to_first_item",
                    run_id=run_id,
                    reason="no_current_item_fallback_to_list",
                )

        # Calculate average confidence
        ref_count = len(references.references)
        avg_confidence = total_confidence / ref_count if ref_count > 0 else 0.0

        # NOTE: source_domain already detected at start of method via _detect_domain_for_ordinal_resolution
        # No need to re-detect here - the legacy code was removed in 2025-01 refactoring

        logger.debug(
            "references_resolved",
            run_id=run_id,
            resolved_count=len(resolved_items),
            total_items=len(all_items),
            confidence=round(avg_confidence, 2),
            source_domain=source_domain,
        )

        return ResolvedContext(
            items=resolved_items,
            confidence=avg_confidence,
            method=resolution_method,
            source_turn_id=last_list_turn,
            source_domain=source_domain,
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

    def _detect_domain_for_ordinal_resolution(
        self,
        state: MessagesState,
        run_id: str,
    ) -> str | None:
        """
        Detect domain for ordinal resolution ("detail du 2ème").

        Priority order:
        1. routing_history[-1].domains - Domain detected by router for CURRENT turn
           (Handles explicit override: "detail du 1er contact" after "recherche taches")
        2. STATE_KEY_LAST_LIST_DOMAIN - Fallback to last search/list action domain
           (Used when router doesn't detect explicit domain in query)

        Example flows:
            Flow 1 - Implicit (same domain):
                Turn 1: "recherche contacts" → router: ["contacts"], last_list_domain = "contacts"
                Turn 2: "detail du premier"  → router: ["contacts"], uses "contacts" ✅

            Flow 2 - Explicit override (different domain):
                Turn 1: "recherche taches"   → router: ["tasks"], last_list_domain = "tasks"
                Turn 2: "detail du 1er contact" → router: ["contacts"], uses "contacts" ✅
                        (Router detects "contact" in query, overrides last_list_domain)

            Flow 3 - No explicit domain, uses last list:
                Turn 1: "recherche contacts" → router: ["contacts"], last_list_domain = "contacts"
                Turn 2: "salut ca va?"       → router: [], last_list_domain = "contacts" (unchanged)
                Turn 3: "detail du premier"  → router: [], uses "contacts" from last_list_domain ✅

        Args:
            state: Current conversation state.
            run_id: Run ID for logging.

        Returns:
            Domain name (e.g., "contacts", "emails") or None if not found.
        """
        # PRIORITY 1: Use routing_history[-1].domains (current turn's detected domain)
        # This handles explicit override: "detail du 1er contact" after "recherche taches"
        # The router detects "contact" in the query and sets domains=["contacts"]
        routing_history = state.get(STATE_KEY_ROUTING_HISTORY, [])
        if routing_history:
            last_route = routing_history[-1]  # type: ignore

            # Extract domains from RouterOutput
            domains: list[str] = []
            if hasattr(last_route, "domains"):
                domains = last_route.domains or []
            elif isinstance(last_route, dict):
                domains = last_route.get("domains", [])

            if domains:
                primary_domain = domains[0]
                logger.debug(
                    "detect_domain_from_routing_history",
                    run_id=run_id,
                    primary_domain=primary_domain,
                    all_domains=domains,
                    source="routing_history[-1] (explicit override)",
                )
                return primary_domain

        # PRIORITY 2: Fallback to last_list_domain from state
        # Used when router doesn't detect explicit domain (e.g., "detail du premier")
        last_list_domain = state.get(STATE_KEY_LAST_LIST_DOMAIN)
        if last_list_domain:
            logger.debug(
                "detect_domain_from_last_list_domain",
                run_id=run_id,
                domain=last_list_domain,
                source="STATE_KEY_LAST_LIST_DOMAIN (fallback)",
            )
            return last_list_domain  # type: ignore

        logger.debug(
            "detect_domain_no_source_found",
            run_id=run_id,
            has_routing_history=bool(routing_history),
            has_last_list_domain=bool(last_list_domain),
        )
        return None

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

    def determine_turn_type(
        self,
        query: str,
        router_action: str,
        has_references: bool,
    ) -> str:
        """
        Determine the type of turn based on context.

        Args:
            query: User query text.
            router_action: Router decision (e.g., "conversational", "actionable").
            has_references: Whether query contains references.

        Returns:
            Turn type: "action", "reference", or "conversational".
        """
        if has_references:
            return TURN_TYPE_REFERENCE
        elif router_action.lower() in ["conversational", "conversation"]:
            return TURN_TYPE_CONVERSATIONAL
        else:
            return TURN_TYPE_ACTION


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
