"""
HITL Policy Classes Package.

This package contains Policy Classes for HITL decision building.

Policy Classes (Composition Pattern):
1. ClassificationExtractor - Extract classification data from results
2. RejectionDecisionBuilder - Build rejection decisions with metrics
3. EditDecisionBuilder - Build edit decisions with parameter merging
4. ApprovalDecisionBuilder - Orchestrate decision building (composes others)

Architecture:
- Composition over Inheritance: Builders compose each other
- Single Responsibility: Each policy has one clear purpose
- DRY: Shared logic extracted from HITLOrchestrator
"""

from src.domains.agents.services.hitl.policies.approval_decision_builder import (
    ApprovalDecisionBuilder,
)
from src.domains.agents.services.hitl.policies.classification_extractor import (
    ClassificationExtractor,
)
from src.domains.agents.services.hitl.policies.edit_decision_builder import (
    EditDecisionBuilder,
)
from src.domains.agents.services.hitl.policies.rejection_decision_builder import (
    RejectionDecisionBuilder,
)

__all__ = [
    "ClassificationExtractor",
    "RejectionDecisionBuilder",
    "EditDecisionBuilder",
    "ApprovalDecisionBuilder",
]
