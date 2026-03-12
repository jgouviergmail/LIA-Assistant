"""
Planning Result - Shared dataclass for planning strategies.

This module contains the PlanningResult dataclass used by all planning strategies
to return plan generation results with metadata.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domains.agents.orchestration.plan_schemas import ExecutionPlan
    from src.domains.agents.services.smart_catalogue_service import FilteredCatalogue


@dataclass
class PlanningResult:
    """
    Result of smart planning.

    Attributes:
        plan: Generated execution plan (None if planning failed)
        success: Whether planning succeeded
        error: Error message if planning failed
        tokens_used: Estimated tokens used in planning
        tokens_saved: Estimated tokens saved vs full catalogue
        used_template: Whether template-based planning was used
        used_panic_mode: Whether panic mode (expanded catalogue) was used
        used_generative: Whether generative multi-domain planning was used
        filtered_catalogue: Filtered catalogue used (for debug panel)
    """

    plan: "ExecutionPlan | None"
    success: bool
    error: str | None = None
    tokens_used: int = 0
    tokens_saved: int = 0  # Compared to full catalogue
    used_template: bool = False
    used_panic_mode: bool = False
    used_generative: bool = False
    filtered_catalogue: "FilteredCatalogue | None" = None  # For debug panel


__all__ = [
    "PlanningResult",
]
