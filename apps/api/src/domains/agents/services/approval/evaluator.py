"""
Évaluateur d'approbation pour plans d'exécution.

Ce module orchestre l'évaluation de plusieurs stratégies d'approbation
pour déterminer si un plan nécessite une approbation utilisateur.
"""

import structlog

from src.domains.agents.orchestration.approval_schemas import ApprovalEvaluation
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan
from src.domains.agents.orchestration.validator import ValidationContext
from src.domains.agents.services.approval.strategies import ApprovalStrategy

logger = structlog.get_logger(__name__)


class ApprovalEvaluator:
    """
    Évaluateur d'approbation pour plans d'exécution.

    Exécute une liste de stratégies d'approbation et agrège les résultats
    pour déterminer si un plan nécessite approbation.
    """

    def __init__(self, strategies: list[ApprovalStrategy]):
        """
        Initialize evaluator.

        Args:
            strategies: Liste de stratégies à évaluer
        """
        self.strategies = strategies

    def evaluate(self, plan: ExecutionPlan, context: ValidationContext) -> ApprovalEvaluation:
        """
        Évalue si le plan nécessite approbation.

        Exécute toutes les stratégies et combine les résultats.
        Si au moins une stratégie se déclenche, approbation requise.

        Args:
            plan: Plan d'exécution à évaluer
            context: Contexte de validation

        Returns:
            ApprovalEvaluation avec décision et détails
        """
        reasons = []
        strategies_triggered = []
        details = {}

        for _i, strategy in enumerate(self.strategies):
            strategy_name = strategy.__class__.__name__

            try:
                requires, reason = strategy.requires_approval(plan, context)

                if requires:
                    strategies_triggered.append(strategy_name)
                    if reason:
                        reasons.append(reason)

                details[strategy_name] = {
                    "triggered": requires,
                    "reason": reason,
                }

                logger.debug(
                    "strategy_evaluated",
                    plan_id=plan.plan_id,
                    strategy=strategy_name,
                    triggered=requires,
                    reason=reason,
                )

            except Exception as e:
                logger.error(
                    "strategy_evaluation_failed",
                    plan_id=plan.plan_id,
                    strategy=strategy_name,
                    error=str(e),
                    exc_info=True,
                )
                # Continue with other strategies

        # Final decision: if at least one strategy triggers
        requires_approval = len(strategies_triggered) > 0

        evaluation = ApprovalEvaluation(
            requires_approval=requires_approval,
            reasons=reasons,
            strategies_triggered=strategies_triggered,
            details=details,
        )

        logger.info(
            "approval_evaluation_complete",
            plan_id=plan.plan_id,
            requires_approval=requires_approval,
            strategies_triggered=strategies_triggered,
            reason_count=len(reasons),
        )

        return evaluation
