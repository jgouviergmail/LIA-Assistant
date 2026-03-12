"""
Base Strategy Protocol for SmartPlannerService.

This module defines the interface that all planning strategies must implement.
Uses Protocol (structural subtyping) instead of ABC for flexibility.

Architecture:
- Protocol defines can_handle() and plan() methods
- Strategies implement Protocol without explicit inheritance
- SmartPlannerService orchestrates via strategy selection
"""

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from src.domains.agents.analysis.query_intelligence import QueryIntelligence
    from src.domains.agents.services.planner.planning_result import PlanningResult
    from src.domains.agents.services.smart_catalogue_service import FilteredCatalogue


class PlanningStrategy(Protocol):
    """
    Protocol for planning strategies.

    All planning strategies must implement:
    1. can_handle() - Check if strategy can handle the request
    2. plan() - Execute planning logic

    This Protocol allows duck typing - any class implementing these methods
    is automatically considered a valid strategy.
    """

    async def can_handle(
        self,
        intelligence: "QueryIntelligence",
        catalogue: "FilteredCatalogue | None" = None,
    ) -> bool:
        """
        Check if this strategy can handle the given intelligence.

        Args:
            intelligence: QueryIntelligence with user intent analysis
            catalogue: Optional filtered catalogue for context

        Returns:
            True if this strategy can handle the request, False otherwise
        """
        ...

    async def plan(
        self,
        intelligence: "QueryIntelligence",
        config: "RunnableConfig",
        catalogue: "FilteredCatalogue | None" = None,
        validation_feedback: str | None = None,
        clarification_response: str | None = None,
        clarification_field: str | None = None,
        existing_plan: "Any | None" = None,
    ) -> "PlanningResult":
        """
        Execute planning strategy.

        Args:
            intelligence: QueryIntelligence with user intent analysis
            config: RunnableConfig for LangGraph
            catalogue: Filtered catalogue (if applicable)
            validation_feedback: Feedback from semantic validation
            clarification_response: User's response to clarification
            clarification_field: Specific field clarified
            existing_plan: Previous plan to preserve parameters from

        Returns:
            PlanningResult with plan and metadata
        """
        ...


__all__ = [
    "PlanningStrategy",
]
