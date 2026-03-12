"""
Planning Utilities - Shared helper functions for planning strategies.

This module contains utility functions used by multiple planning strategies
to build plans, create virtual catalogues, and extract item IDs.
"""

from typing import TYPE_CHECKING, Any

from src.domains.agents.services.planner.domain_constants import DOMAIN_ID_FIELDS
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from src.domains.agents.analysis.query_intelligence import QueryIntelligence
    from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep
    from src.domains.agents.services.smart_catalogue_service import FilteredCatalogue

logger = get_logger(__name__)


def build_plan_from_steps(
    steps: list["ExecutionStep"],
    intelligence: "QueryIntelligence",
    config: "RunnableConfig",
    catalogue_service: Any = None,
) -> "ExecutionPlan":
    """
    Build ExecutionPlan from steps.

    Args:
        steps: List of execution steps
        intelligence: QueryIntelligence with user intent
        config: RunnableConfig for extracting session/user info
        catalogue_service: Optional catalogue service for metrics

    Returns:
        ExecutionPlan with metadata
    """
    from src.domains.agents.nodes.utils import extract_session_id_from_config
    from src.domains.agents.orchestration.plan_schemas import ExecutionPlan

    configurable = config.get("configurable", {})

    # Get tokens saved from catalogue service if available
    tokens_saved = 0
    if catalogue_service:
        tokens_saved = catalogue_service.get_metrics().tokens_saved

    return ExecutionPlan(
        plan_id=f"smart_{configurable.get('run_id', 'unknown')}",
        user_id=str(configurable.get("user_id", "")),
        session_id=extract_session_id_from_config(config, required=False) or "",
        steps=steps,
        execution_mode="sequential",
        metadata={
            "smart_planner": True,
            "intent": intelligence.immediate_intent,
            "domains": intelligence.domains,
            "user_goal": intelligence.user_goal.value,
            "tokens_estimate": tokens_saved,
            # FOR_EACH HITL: Propagate cardinality from query analysis
            "cardinality_magnitude": intelligence.cardinality_magnitude,
            "for_each_detected": intelligence.for_each_detected,
        },
    )


def create_virtual_catalogue(
    tool_names: list[str],
    domains: list[str],
    is_bypass: bool = False,
) -> "FilteredCatalogue":
    """
    Create a virtual catalogue for bypass scenarios.

    This provides debug panel visibility even when LLM planning is bypassed.

    Args:
        tool_names: List of tool names used in the bypass
        domains: List of domains involved
        is_bypass: True if from template bypass

    Returns:
        FilteredCatalogue with minimal tool info for debug panel
    """
    from src.domains.agents.services.smart_catalogue_service import FilteredCatalogue

    # Create minimal tool dicts
    virtual_tools = []
    for tool_name in tool_names:
        # Extract domain from tool name (e.g., "get_contacts_tool" → "contacts")
        domain = "unknown"
        for d in domains:
            if d in tool_name:
                domain = d
                break

        virtual_tools.append(
            {
                "name": tool_name,
                "agent": f"{domain}_agent",
                "description": f"(Bypass) {tool_name}",
            }
        )

    return FilteredCatalogue(
        tools=virtual_tools,
        tool_count=len(virtual_tools),
        token_estimate=0,  # No tokens (bypass)
        domains_included=domains,
        categories_included=["bypass_template"] if is_bypass else [],
        is_panic_mode=False,
    )


def extract_item_id(item: Any, domain: str) -> str | None:
    """
    Extract the item ID from a resolved item based on domain.

    Tries multiple field names in order until finding a valid ID.

    Args:
        item: Resolved item (dict)
        domain: Domain name (e.g., "contacts", "emails")

    Returns:
        Item ID as string, or None if not found
    """
    if not isinstance(item, dict):
        return None

    id_fields = DOMAIN_ID_FIELDS.get(domain, ["_registry_id"])
    for field in id_fields:
        if field in item and item[field]:
            return str(item[field])

    return None


__all__ = [
    "build_plan_from_steps",
    "create_virtual_catalogue",
    "extract_item_id",
]
