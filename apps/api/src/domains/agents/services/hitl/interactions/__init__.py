"""
HITL Interaction Implementations.

This package contains concrete implementations of HitlInteractionProtocol
for different HITL interaction types.

Available Interactions:
    - PlanApprovalInteraction: Plan-level approval (plan_approval)
    - ToolConfirmationInteraction: Tool-level confirmation (tool_confirmation)
    - ClarificationInteraction: Clarification requests (clarification) - Phase 2
    - DraftCritiqueInteraction: Draft review before execution (draft_critique) - Data Registry LOT 4.3

Auto-Registration:
    Interactions are auto-registered with HitlInteractionRegistry when imported.
    Import this package to ensure all interactions are available.

Usage:
    >>> from src.domains.agents.services.hitl.interactions import (
    ...     PlanApprovalInteraction,
    ...     DraftCritiqueInteraction,
    ... )
    >>> # Or use registry
    >>> from src.domains.agents.services.hitl.registry import HitlInteractionRegistry
    >>> interaction = HitlInteractionRegistry.get(HitlInteractionType.DRAFT_CRITIQUE)

Created: 2025-11-25
Updated: 2025-11-26 (Data Registry LOT 4.3 - DraftCritiqueInteraction)
"""

# Import interactions to trigger auto-registration
from .clarification import ClarificationInteraction
from .destructive_confirm import DestructiveConfirmInteraction
from .draft_critique import DraftCritiqueInteraction
from .entity_disambiguation import EntityDisambiguationInteraction
from .for_each_confirmation import ForEachConfirmationInteraction
from .plan_approval import PlanApprovalInteraction
from .tool_confirmation import ToolConfirmationInteraction

__all__ = [
    "PlanApprovalInteraction",
    "ToolConfirmationInteraction",
    "ClarificationInteraction",  # Phase 2 OPTIMPLAN
    "DraftCritiqueInteraction",  # Data Registry LOT 4.3
    "EntityDisambiguationInteraction",  # Entity resolution disambiguation
    "DestructiveConfirmInteraction",  # Phase 3: Bulk operation safety
    "ForEachConfirmationInteraction",  # For-each bulk iteration confirmation
]
