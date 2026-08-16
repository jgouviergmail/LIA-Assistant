"""
HITL (Human-in-the-Loop) service layer.

Components:
- resumption_strategies.py: Helpers consumed by the production resume path
  (orchestration/service.py builds the Command, streaming/service.py streams —
  the unwired strategy-class layer was deleted, see ADR-222)
- interactions/: HITL interaction implementations (registry-driven, Phase 1)
- schemas.py / validator.py / registry.py: interrupt payload contracts,
  validation and the interaction registry
- question_generator.py / draft_modifier.py: LLM-backed interaction content

The LLM response classifier lives one level up (services/hitl_classifier.py).
"""

# CRITICAL: Import interactions to trigger @register decorators
# Phase 1 OPTIMPLAN: PlanApprovalInteraction auto-registers with HitlInteractionRegistry
from src.domains.agents.services.hitl import interactions  # noqa: F401
from src.domains.agents.services.hitl.schemas import (
    STANDARD_DESTRUCTIVE_ACTIONS,
    STANDARD_DRAFT_ACTIONS,
    STANDARD_PLAN_ACTIONS,
    ClarificationContext,
    DestructiveConfirmContext,
    DraftCritiqueContext,
    HitlAction,
    HitlActionStyle,
    HitlInterruptPayload,
    HitlSeverity,
    HitlUserResponse,
    PlanApprovalContext,
)

__all__ = [
    # Pydantic schemas (Phase 2)
    "ClarificationContext",
    "DestructiveConfirmContext",
    "DraftCritiqueContext",
    "HitlAction",
    "HitlActionStyle",
    "HitlInterruptPayload",
    "HitlSeverity",
    "HitlUserResponse",
    "PlanApprovalContext",
    # Standard action sets
    "STANDARD_DESTRUCTIVE_ACTIONS",
    "STANDARD_DRAFT_ACTIONS",
    "STANDARD_PLAN_ACTIONS",
]
