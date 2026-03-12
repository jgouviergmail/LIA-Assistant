"""
Services d'approbation pour HITL Plan-Level.

Ce package fournit les stratégies et l'évaluateur pour déterminer
si un plan d'exécution nécessite une approbation utilisateur.
"""

from .evaluator import ApprovalEvaluator
from .strategies import (
    ApprovalStrategy,
    CompositeStrategy,
    CostThresholdStrategy,
    DataSensitivityStrategy,
    ManifestBasedStrategy,
    RoleBasedStrategy,
)

__all__ = [
    "ApprovalStrategy",
    "ManifestBasedStrategy",
    "CostThresholdStrategy",
    "DataSensitivityStrategy",
    "RoleBasedStrategy",
    "CompositeStrategy",
    "ApprovalEvaluator",
]
