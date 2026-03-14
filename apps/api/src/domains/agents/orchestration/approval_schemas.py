"""
Schemas for the plan approval system (HITL Plan-Level).

This module defines data structures used to present plans to the user
for approval and to process approval decisions.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class StepSummary(BaseModel):
    """Summary of a plan step for presentation to the user."""

    step_id: str = Field(..., description="Unique step identifier")
    tool_name: str = Field(..., description="Name of the tool to execute")
    description: str = Field(..., description="Description of the action")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Tool parameters")
    estimated_cost_usd: float = Field(
        default=0.0, description="Estimated cost for this step in USD"
    )
    hitl_required: bool = Field(
        default=False, description="This step requires HITL (from manifest)"
    )
    data_classification: str | None = Field(
        None,
        description="Classification of accessed data (PUBLIC, CONFIDENTIAL, etc.)",
    )
    required_scopes: list[str] = Field(default_factory=list, description="Required OAuth scopes")


class PlanSummary(BaseModel):
    """Summary of an execution plan for presentation to the user."""

    plan_id: str = Field(..., description="Unique plan identifier")
    total_steps: int = Field(..., description="Total number of steps")
    total_cost_usd: float = Field(..., description="Total estimated cost in USD")
    hitl_steps_count: int = Field(..., description="Number of steps requiring HITL")
    steps: list[StepSummary] = Field(..., description="Step details")
    generated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Plan generation date"
    )


class PlanApprovalRequest(BaseModel):
    """
    Plan approval request sent to the user.

    This structure is used by approval_gate_node to present
    a complete plan to the user and await their decision.
    """

    plan_summary: PlanSummary = Field(..., description="Summary of the plan to approve")
    approval_reasons: list[str] = Field(
        default_factory=list,
        description="Reasons why this plan requires approval",
    )
    strategies_triggered: list[str] = Field(
        default_factory=list,
        description="Approval strategies triggered (e.g., CostThreshold, ManifestBased)",
    )
    user_message: str | None = Field(
        default=None,
        description="Contextual message for the user (None if deferred generation via streaming)",
    )


class PlanModification(BaseModel):
    """
    Modification to apply to a plan.

    Allows the user to modify step parameters,
    remove steps, or reorder steps.
    """

    modification_type: Literal["edit_params", "remove_step", "reorder_steps"] = Field(
        ..., description="Modification type"
    )
    step_id: str | None = Field(
        None, description="ID of the affected step (edit_params, remove_step)"
    )
    new_parameters: dict[str, Any] | None = Field(None, description="New parameters (edit_params)")
    new_order: list[str] | None = Field(None, description="New step_id order (reorder_steps)")


class PlanApprovalDecision(BaseModel):
    """
    User decision regarding a plan.

    Represents the user's response to an approval request.
    """

    decision: Literal["APPROVE", "REJECT", "EDIT", "REPLAN"] = Field(
        ..., description="Decision type"
    )
    rejection_reason: str | None = Field(None, description="Rejection reason (REJECT)")
    modifications: list[PlanModification] = Field(
        default_factory=list, description="Modifications to apply (EDIT)"
    )
    replan_instructions: str | None = Field(
        None, description="Instructions to regenerate the plan (REPLAN)"
    )
    decided_at: datetime = Field(default_factory=datetime.utcnow, description="Decision date")


class ApprovalEvaluation(BaseModel):
    """
    Result of approval strategy evaluation.

    Used by ApprovalEvaluator to determine if a plan requires approval
    and why.
    """

    requires_approval: bool = Field(..., description="Does the plan require approval?")
    reasons: list[str] = Field(default_factory=list, description="Reasons why approval is required")
    strategies_triggered: list[str] = Field(
        default_factory=list, description="Names of triggered strategies"
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional details (thresholds, values, etc.)",
    )


class PlanApprovalAudit(BaseModel):
    """
    Audit entry for a plan approval decision.

    Used for logging and compliance.
    """

    id: UUID
    plan_id: str
    user_id: UUID
    conversation_id: UUID
    plan_summary: dict[str, Any]
    strategies_triggered: list[str]
    decision: str
    decision_timestamp: datetime
    modifications: dict[str, Any] | None
    rejection_reason: str | None
    approval_latency_seconds: float
    created_at: datetime
