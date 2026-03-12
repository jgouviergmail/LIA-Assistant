"""
Base Strategy Protocol for SmartCatalogueService.

This module defines the interface that all filtering strategies must implement.
Uses Protocol (structural subtyping) instead of ABC for flexibility.

Architecture:
- Protocol defines can_handle() and filter() methods
- Strategies implement Protocol without explicit inheritance
- SmartCatalogueService orchestrates via strategy selection
"""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.domains.agents.analysis.query_intelligence import QueryIntelligence
    from src.domains.agents.services.smart_catalogue_service import FilteredCatalogue


class FilteringStrategy(Protocol):
    """
    Protocol for catalogue filtering strategies.

    All filtering strategies must implement:
    1. can_handle() - Check if strategy can handle the request
    2. filter() - Execute filtering logic

    This Protocol allows duck typing - any class implementing these methods
    is automatically considered a valid strategy.
    """

    def can_handle(
        self,
        intelligence: "QueryIntelligence",
        panic_mode: bool = False,
    ) -> bool:
        """
        Check if this strategy can handle the given intelligence.

        Args:
            intelligence: QueryIntelligence with user intent analysis
            panic_mode: Whether panic mode is requested

        Returns:
            True if this strategy can handle the request, False otherwise
        """
        ...

    def filter(
        self,
        intelligence: "QueryIntelligence",
        tool_selection_result: dict | None = None,
    ) -> "FilteredCatalogue":
        """
        Execute filtering strategy.

        Args:
            intelligence: QueryIntelligence with user intent analysis
            tool_selection_result: Semantic tool scores from router

        Returns:
            FilteredCatalogue with filtered tools
        """
        ...


__all__ = [
    "FilteringStrategy",
]
