"""
HITL (Human-in-the-Loop) service layer.

Architecture:
- Protocol-based design (like OAuthProvider, VectorStoreProvider)
- Strategy pattern for resumption methods
- Extensible for future agent types (Gmail, Calendar, Drive)

Components:
- base.py: Protocol definition (HitlResumptionStrategy)
- resumption_strategies.py: Concrete implementations
- service.py: Orchestrator (classification + routing)
- classifier.py: LLM-based response classifier (migrated)
- patterns.py: Fast-path pattern matching (migrated)
- interactions/: HITL interaction implementations (Phase 1)
"""

# CRITICAL: Import interactions to trigger @register decorators
# Phase 1 OPTIMPLAN: PlanApprovalInteraction auto-registers with HitlInteractionRegistry
from src.domains.agents.services.hitl import interactions  # noqa: F401
from src.domains.agents.services.hitl.base import HitlResumptionStrategy
from src.domains.agents.services.hitl.resumption_strategies import (
    ConversationalHitlResumption,
)
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
    # Resumption strategies
    "ConversationalHitlResumption",
    "HitlResumptionStrategy",
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
