"""
Approval strategies to determine if a plan requires HITL.

This module defines various strategies that can be used alone
or combined to evaluate if an execution plan requires user
approval before execution.
"""

from typing import Protocol

import structlog

from src.core.config import settings
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan
from src.domains.agents.orchestration.validator import ValidationContext
from src.domains.agents.registry import get_global_registry

logger = structlog.get_logger(__name__)


class ApprovalStrategy(Protocol):
    """
    Interface for approval strategies.

    A strategy evaluates if a plan requires approval based on
    a specific criterion (cost, sensitivity, role, etc.).
    """

    def requires_approval(
        self, plan: ExecutionPlan, context: ValidationContext
    ) -> tuple[bool, str]:
        """
        Determine if the plan requires approval according to this strategy.

        Args:
            plan: Execution plan to evaluate
            context: Validation context (user_id, roles, etc.)

        Returns:
            Tuple (requires_approval, reason)
                requires_approval: True if approval is needed
                reason: Explanation why (empty if no approval needed)
        """
        ...


class ManifestBasedStrategy:
    """
    Strategy based on tool manifests.

    Checks if at least one tool in the plan has `permissions.hitl_required = True`
    in its manifest.

    This is the default and primary strategy.
    """

    def requires_approval(
        self, plan: ExecutionPlan, context: ValidationContext
    ) -> tuple[bool, str]:
        """Evaluate based on manifests."""
        registry = get_global_registry()
        hitl_tools = []

        for step in plan.steps:
            # Skip non-TOOL steps
            if not step.tool_name:
                continue

            try:
                manifest = registry.get_tool_manifest(step.tool_name)
                if manifest.permissions.hitl_required:
                    hitl_tools.append(step.tool_name)
            except Exception as e:
                logger.warning(
                    "manifest_check_failed",
                    tool_name=step.tool_name,
                    error=str(e),
                )
                continue

        # Also check step-level override
        steps_with_approval = [step.step_id for step in plan.steps if step.approvals_required]

        if hitl_tools or steps_with_approval:
            reason_parts = []
            if hitl_tools:
                reason_parts.append(f"Tools requiring HITL: {', '.join(hitl_tools)}")
            if steps_with_approval:
                reason_parts.append(f"Steps requiring approval: {', '.join(steps_with_approval)}")

            reason = "; ".join(reason_parts)

            logger.info(
                "manifest_strategy_triggered",
                plan_id=plan.plan_id,
                hitl_tools=hitl_tools,
                approval_steps=steps_with_approval,
            )

            return True, reason

        return False, ""


class CostThresholdStrategy:
    """
    Strategy based on plan cost.

    Requires approval if the total estimated cost exceeds a configurable threshold.
    """

    def __init__(self, threshold_usd: float | None = None):
        """
        Initialize strategy.

        Args:
            threshold_usd: Threshold in USD (None = use config)
        """
        self.threshold_usd = (
            threshold_usd if threshold_usd is not None else settings.approval_cost_threshold_usd
        )

    def requires_approval(
        self, plan: ExecutionPlan, context: ValidationContext
    ) -> tuple[bool, str]:
        """Evaluate based on cost."""
        estimated_cost = plan.estimated_cost_usd or 0.0

        if estimated_cost > self.threshold_usd:
            reason = f"Plan cost ${estimated_cost:.4f} exceeds threshold ${self.threshold_usd:.4f}"

            logger.info(
                "cost_strategy_triggered",
                plan_id=plan.plan_id,
                estimated_cost=estimated_cost,
                threshold=self.threshold_usd,
            )

            return True, reason

        return False, ""


class DataSensitivityStrategy:
    """
    Strategy based on data classification.

    Requires approval if the plan accesses data classified
    as sensitive (CONFIDENTIAL, RESTRICTED, etc.).
    """

    def __init__(self, sensitive_levels: list[str] | None = None):
        """
        Initialize strategy.

        Args:
            sensitive_levels: Sensitive levels (None = use config)
        """
        self.sensitive_levels = (
            sensitive_levels
            if sensitive_levels is not None
            else settings.approval_sensitive_classifications
        )

    def requires_approval(
        self, plan: ExecutionPlan, context: ValidationContext
    ) -> tuple[bool, str]:
        """Evaluate based on data classification."""
        registry = get_global_registry()
        sensitive_tools = []

        for step in plan.steps:
            if not step.tool_name:
                continue

            try:
                manifest = registry.get_tool_manifest(step.tool_name)
                classification = manifest.permissions.data_classification

                if classification in self.sensitive_levels:
                    sensitive_tools.append(f"{step.tool_name} ({classification})")
            except Exception as e:
                logger.warning(
                    "data_classification_check_failed",
                    tool_name=step.tool_name,
                    error=str(e),
                )
                continue

        if sensitive_tools:
            reason = f"Accessing sensitive data: {', '.join(sensitive_tools)}"

            logger.info(
                "data_sensitivity_strategy_triggered",
                plan_id=plan.plan_id,
                sensitive_tools=sensitive_tools,
            )

            return True, reason

        return False, ""


class RoleBasedStrategy:
    """
    Strategy based on user role.

    Certain roles (admin, power_user) can auto-approve,
    while other users require approval.
    """

    def __init__(self, auto_approve_roles: list[str] | None = None):
        """
        Initialize strategy.

        Args:
            auto_approve_roles: Roles that auto-approve (None = use config)
        """
        self.auto_approve_roles = (
            auto_approve_roles
            if auto_approve_roles is not None
            else settings.approval_auto_approve_roles
        )

    def requires_approval(
        self, plan: ExecutionPlan, context: ValidationContext
    ) -> tuple[bool, str]:
        """Evaluate based on user role."""
        user_roles = context.user_roles or []

        # If user has an auto-approve role, no approval needed
        has_auto_approve_role = any(role in self.auto_approve_roles for role in user_roles)

        if has_auto_approve_role:
            logger.info(
                "role_strategy_auto_approved",
                plan_id=plan.plan_id,
                user_roles=user_roles,
                auto_approve_roles=self.auto_approve_roles,
            )
            return False, ""

        # Otherwise, approval required
        reason = f"User roles {user_roles} require approval"

        logger.info(
            "role_strategy_triggered",
            plan_id=plan.plan_id,
            user_roles=user_roles,
        )

        return True, reason


class CompositeStrategy:
    """
    Composite strategy combining multiple strategies.

    Allows combining multiple strategies with AND or OR logic.

    Examples:
        # Requires ALL strategies to trigger
        strategy = CompositeStrategy(
            strategies=[ManifestBased(), CostThreshold()],
            require_all=True
        )

        # Requires ANY strategy to trigger
        strategy = CompositeStrategy(
            strategies=[ManifestBased(), DataSensitivity()],
            require_all=False
        )
    """

    def __init__(
        self,
        strategies: list[ApprovalStrategy],
        require_all: bool = False,
    ):
        """
        Initialize composite strategy.

        Args:
            strategies: List of strategies to combine
            require_all: If True, all strategies must trigger (AND)
                        If False, at least one strategy must trigger (OR)
        """
        self.strategies = strategies
        self.require_all = require_all

    def requires_approval(
        self, plan: ExecutionPlan, context: ValidationContext
    ) -> tuple[bool, str]:
        """Evaluate by combining all strategies."""
        results = []
        reasons = []

        for strategy in self.strategies:
            requires, reason = strategy.requires_approval(plan, context)
            results.append(requires)
            if reason:
                reasons.append(reason)

        if self.require_all:
            # AND logic: all must trigger
            requires_approval = all(results)
        else:
            # OR logic: at least one must trigger
            requires_approval = any(results)

        combined_reason = "; ".join(reasons) if reasons else ""

        logger.info(
            "composite_strategy_evaluated",
            plan_id=plan.plan_id,
            require_all=self.require_all,
            strategy_results=results,
            final_decision=requires_approval,
        )

        return requires_approval, combined_reason
