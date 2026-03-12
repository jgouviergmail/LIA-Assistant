"""
Reference Bypass Strategy - Bypass LLM for pure reference resolution.

This strategy handles simple "detail of the first/second/..." queries where
the item has already been resolved by reference resolution middleware.

Examples:
- "Details of the first" (after previous contact search)
- "Show me the second email" (after previous email listing)
- "Open the first, second and third" (multi-ordinal with resolved items)

Architecture:
- Checks if query is REFERENCE_PURE with "search" intent
- Verifies resolved_context has valid item IDs
- Creates ExecutionPlan directly without LLM call
- Handles both single and batch item modes

Benefits:
- Zero LLM tokens used
- Instant plan generation (~0ms vs ~500ms)
- No risk of LLM hallucinating invalid tool names
"""

from typing import TYPE_CHECKING, Any

from src.domains.agents.services.planner.domain_constants import (
    DOMAIN_BATCH_PARAM_NAMES,
    DOMAIN_GET_TOOLS,
    DOMAIN_PARAM_NAMES,
)
from src.domains.agents.services.planner.planner_utils import (
    build_plan_from_steps,
    create_virtual_catalogue,
    extract_item_id,
)
from src.domains.agents.services.planner.planning_result import PlanningResult
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from src.domains.agents.analysis.query_intelligence import QueryIntelligence
    from src.domains.agents.services.smart_catalogue_service import FilteredCatalogue

logger = get_logger(__name__)


class ReferenceBypassStrategy:
    """
    Planning strategy for pure reference resolution queries.

    Bypasses LLM when user asks for details of resolved references like
    "first", "second", "all three", etc.

    requires_catalogue = False: bypass group (no filtered catalogue needed).
    """

    requires_catalogue = False

    async def can_handle(
        self,
        intelligence: "QueryIntelligence",
        catalogue: "FilteredCatalogue | None" = None,
    ) -> bool:
        """
        Check if we can bypass LLM for resolved reference queries.

        Bypass is possible when:
        1. turn_type is REFERENCE_PURE (not a mutation)
        2. intent is "search" (unified intent for all data retrieval)
        3. resolved_context has items with valid IDs
        4. source_domain is supported for bypass
        5. NOT a cross-domain query (no other domains involved)

        Args:
            intelligence: QueryIntelligence with user intent
            catalogue: Not used for this strategy

        Returns:
            True if bypass is possible, False otherwise
        """
        # Must be a pure reference query
        if intelligence.turn_type != "REFERENCE_PURE":
            return False

        # Intent must be search (unified intent covering search/list/detail)
        if intelligence.immediate_intent != "search":
            return False

        # Cross-domain check: don't bypass if other domains are involved
        # When user references an item but wants action in ANOTHER domain,
        # LLM planning is required to chain the operations correctly
        source_domain = intelligence.source_domain
        if source_domain and intelligence.domains:
            # Check if any domain OTHER than source is involved
            other_domains = [d for d in intelligence.domains if d != source_domain]
            if other_domains:
                logger.debug(
                    "reference_bypass_skipped_cross_domain",
                    source_domain=source_domain,
                    other_domains=other_domains,
                    reason="Cross-domain query requires LLM planning",
                )
                return False

        # Must have resolved context with items
        if not intelligence.resolved_context:
            return False

        resolved = intelligence.resolved_context
        if isinstance(resolved, dict):
            items = resolved.get("items", [])
        else:
            # ResolvedContext object
            items = getattr(resolved, "items", [])

        if not items:
            return False

        # Source domain must be supported
        if not source_domain or source_domain not in DOMAIN_GET_TOOLS:
            return False

        # Extract item ID to verify it's valid
        first_item = items[0]
        item_id = extract_item_id(first_item, source_domain)
        if not item_id:
            logger.debug(
                "reference_bypass_no_item_id",
                source_domain=source_domain,
                item_keys=list(first_item.keys()) if isinstance(first_item, dict) else [],
            )
            return False

        logger.debug(
            "reference_bypass_eligible",
            source_domain=source_domain,
            item_id=item_id[:50] if item_id else None,
            intent=intelligence.immediate_intent,
        )
        return True

    async def plan(
        self,
        intelligence: "QueryIntelligence",
        config: "RunnableConfig",
        catalogue: "FilteredCatalogue | None" = None,
        validation_feedback: str | None = None,
        clarification_response: str | None = None,
        clarification_field: str | None = None,
        existing_plan: "Any | None" = None,
    ) -> PlanningResult:
        """
        Create execution plan directly from resolved reference.

        This bypasses LLM for simple "detail of the first/second/..." queries
        where the item has already been resolved.

        Multi-ordinal fix (2026-01): Handles multiple resolved items.
        - If single item: uses single parameter (e.g., message_id)
        - If multiple items: uses batch parameter (e.g., message_ids)

        Args:
            intelligence: QueryIntelligence with resolved references
            config: RunnableConfig for LangGraph
            catalogue: Not used (bypass doesn't need catalogue)
            validation_feedback: Not used
            clarification_response: Not used
            clarification_field: Not used
            existing_plan: Not used

        Returns:
            PlanningResult with direct plan, or None if bypass not possible
        """
        from src.domains.agents.orchestration.plan_schemas import ExecutionStep, StepType

        source_domain = intelligence.source_domain
        if not source_domain:
            return PlanningResult(
                success=False,
                plan=None,
                error="No source domain for reference bypass",
            )

        # Get resolved items
        resolved = intelligence.resolved_context
        if isinstance(resolved, dict):
            items = resolved.get("items", [])
        else:
            items = getattr(resolved, "items", [])

        if not items:
            return PlanningResult(
                success=False,
                plan=None,
                error="No resolved items for reference bypass",
            )

        # Get tool name for this domain
        tool_name = DOMAIN_GET_TOOLS.get(source_domain)
        if not tool_name:
            return PlanningResult(
                success=False,
                plan=None,
                error=f"No tool found for domain {source_domain}",
            )

        # MULTI-ORDINAL FIX: Handle single vs multiple items
        if len(items) == 1:
            # Single item: use single parameter
            first_item = items[0]
            item_id = extract_item_id(first_item, source_domain)
            if not item_id:
                return PlanningResult(
                    success=False,
                    plan=None,
                    error="Could not extract item ID",
                )

            param_name = DOMAIN_PARAM_NAMES.get(source_domain)
            if not param_name:
                return PlanningResult(
                    success=False,
                    plan=None,
                    error=f"No parameter name for domain {source_domain}",
                )

            parameters = {param_name: item_id}
            log_item_id = item_id[:50] if item_id else None
            log_mode = "single"
        else:
            # Multiple items: use batch parameter
            item_ids = []
            for item in items:
                item_id = extract_item_id(item, source_domain)
                if item_id:
                    item_ids.append(item_id)

            if not item_ids:
                return PlanningResult(
                    success=False,
                    plan=None,
                    error="Could not extract any item IDs",
                )

            batch_param_name = DOMAIN_BATCH_PARAM_NAMES.get(source_domain)
            if not batch_param_name:
                # Fallback to single mode with first item only
                param_name = DOMAIN_PARAM_NAMES.get(source_domain)
                if not param_name:
                    return PlanningResult(
                        success=False,
                        plan=None,
                        error=f"No parameter name for domain {source_domain}",
                    )
                parameters = {param_name: item_ids[0]}
                log_item_id = item_ids[0][:50] if item_ids[0] else None
                log_mode = "single_fallback"
            else:
                parameters = {batch_param_name: item_ids}  # type: ignore
                log_item_id = f"{len(item_ids)} items"
                log_mode = "batch"

        # Create step directly without LLM
        step = ExecutionStep(
            step_id="step_1",
            step_type=StepType.TOOL,
            agent_name=f"{source_domain}_agent",
            tool_name=tool_name,
            parameters=parameters,
            depends_on=[],
        )

        plan = build_plan_from_steps([step], intelligence, config)

        logger.info(
            "reference_bypass_plan_created",
            domain=source_domain,
            tool=tool_name,
            item_id=log_item_id,
            mode=log_mode,
            item_count=len(items),
        )

        # Create virtual catalogue for debug panel
        virtual_catalogue = create_virtual_catalogue(
            tool_names=[tool_name],
            domains=[source_domain],
            is_bypass=True,
        )

        return PlanningResult(
            success=True,
            plan=plan,
            error=None,
            used_panic_mode=False,
            used_template=True,  # Mark as template (no LLM)
            tokens_used=0,
            tokens_saved=500,  # Estimated savings
            filtered_catalogue=virtual_catalogue,  # For debug panel
        )


__all__ = [
    "ReferenceBypassStrategy",
]
