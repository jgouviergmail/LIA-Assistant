"""
Cross-Domain Bypass Strategy - Bypass LLM for cross-domain reference queries.

This strategy handles queries where a user references an item from one domain
but wants to perform an action in another domain, where the required value
is already present in the resolved item.

Examples:
- "search for the restaurant of this meeting" → event.location → places.search
- "find directions to that address" → contact.address → routes.search

Architecture:
- Checks if query is REFERENCE_ACTION with resolved context
- Verifies resolved item has a field that maps to target domain
- Creates ExecutionPlan directly without LLM call
- Uses CROSS_DOMAIN_MAPPINGS for field → domain mapping

Benefits:
- Zero LLM tokens used
- Instant plan generation (~0ms vs ~800ms for multi-domain)
- No risk of LLM misunderstanding cross-domain relationships
"""

from typing import TYPE_CHECKING, Any

from src.domains.agents.services.planner.domain_constants import CROSS_DOMAIN_MAPPINGS
from src.domains.agents.services.planner.planner_utils import (
    build_plan_from_steps,
    create_virtual_catalogue,
)
from src.domains.agents.services.planner.planning_result import PlanningResult
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from src.domains.agents.analysis.query_intelligence import QueryIntelligence
    from src.domains.agents.services.smart_catalogue_service import FilteredCatalogue

logger = get_logger(__name__)


class CrossDomainBypassStrategy:
    """
    Planning strategy for cross-domain reference queries.

    Bypasses LLM when user references an item from one domain but wants
    action in another domain, and the required value exists in the item.

    requires_catalogue = False: bypass group (no filtered catalogue needed).
    """

    requires_catalogue = False

    async def can_handle(
        self,
        intelligence: "QueryIntelligence",
        catalogue: "FilteredCatalogue | None" = None,
    ) -> bool:
        """
        Check if we can bypass LLM for cross-domain resolved reference queries.

        Bypass is possible when:
        1. turn_type is REFERENCE_ACTION (reference + action in another domain)
        2. resolved_context has exactly 1 item
        3. The item has a field that maps to the target domain
        4. The target domain matches primary_domain

        Example:
        - "search for the restaurant of this meeting"
        - turn_type = REFERENCE_ACTION
        - resolved_context = calendar event with location="Restaurant La Table"
        - primary_domain = places
        → Bypass: get_places_tool(query="Restaurant La Table")

        Args:
            intelligence: QueryIntelligence with user intent
            catalogue: Not used for this strategy

        Returns:
            True if bypass is possible, False otherwise
        """
        # Must be a reference action (cross-domain)
        if intelligence.turn_type != "REFERENCE_ACTION":
            return False

        # Must be search intent (looking for something in target domain)
        if intelligence.immediate_intent != "search":
            return False

        # Must have resolved context
        if not intelligence.resolved_context:
            return False

        resolved = intelligence.resolved_context
        if isinstance(resolved, dict):
            items = resolved.get("items", [])
        else:
            items = getattr(resolved, "items", [])

        # Must have exactly 1 item (simple case)
        if len(items) != 1:
            return False

        item = items[0]
        if not isinstance(item, dict):
            return False

        # Check if item has a mappable field
        for field, (target_domain, _, _) in CROSS_DOMAIN_MAPPINGS.items():
            if field in item and item[field]:
                # Target domain must match primary_domain
                if intelligence.primary_domain == target_domain:
                    logger.debug(
                        "cross_domain_bypass_eligible",
                        source_domain=intelligence.source_domain,
                        target_domain=target_domain,
                        field=field,
                        value=str(item[field])[:50],
                    )
                    return True

        return False

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
        Create execution plan directly from cross-domain resolved reference.

        This bypasses LLM for simple "search X of this Y" queries where
        the resolved item contains the value to search.

        Args:
            intelligence: QueryIntelligence with resolved references
            config: RunnableConfig for LangGraph
            catalogue: Not used (bypass doesn't need catalogue)
            validation_feedback: Not used
            clarification_response: Not used
            clarification_field: Not used
            existing_plan: Not used

        Returns:
            PlanningResult with direct plan, or error if bypass not possible
        """
        from src.domains.agents.orchestration.plan_schemas import ExecutionStep, StepType

        # Get resolved item
        resolved = intelligence.resolved_context
        if isinstance(resolved, dict):
            items = resolved.get("items", [])
        else:
            items = getattr(resolved, "items", [])

        if not items:
            return PlanningResult(
                success=False,
                plan=None,
                error="No resolved items for cross-domain bypass",
            )

        item = items[0]
        if not isinstance(item, dict):
            return PlanningResult(
                success=False,
                plan=None,
                error="Resolved item is not a dict",
            )

        # Find the mappable field
        field_used = None
        search_value = None
        tool_name = None
        param_name = None

        for field, (target_domain, tool, param) in CROSS_DOMAIN_MAPPINGS.items():
            if field in item and item[field] and intelligence.primary_domain == target_domain:
                field_used = field
                search_value = str(item[field])
                tool_name = tool
                param_name = param
                break

        if not search_value or not tool_name:
            return PlanningResult(
                success=False,
                plan=None,
                error="No mappable field found for cross-domain bypass",
            )

        # Create step directly without LLM
        step = ExecutionStep(
            step_id="step_1",
            step_type=StepType.TOOL,
            agent_name=f"{intelligence.primary_domain}_agent",
            tool_name=tool_name,
            parameters={param_name: search_value},  # type: ignore
            depends_on=[],
        )

        plan = build_plan_from_steps([step], intelligence, config)

        logger.info(
            "cross_domain_bypass_plan_created",
            source_domain=intelligence.source_domain,
            target_domain=intelligence.primary_domain,
            tool=tool_name,
            field=field_used,
            value=search_value[:50] if search_value else None,
        )

        # Create virtual catalogue for debug panel
        virtual_catalogue = create_virtual_catalogue(
            tool_names=[tool_name],
            domains=[intelligence.primary_domain] if intelligence.primary_domain else [],
            is_bypass=True,
        )

        return PlanningResult(
            success=True,
            plan=plan,
            error=None,
            used_panic_mode=False,
            used_template=True,  # Mark as template (no LLM)
            tokens_used=0,
            tokens_saved=1000,  # Higher savings (avoided multi-domain LLM)
            filtered_catalogue=virtual_catalogue,  # For debug panel
        )


__all__ = [
    "CrossDomainBypassStrategy",
]
