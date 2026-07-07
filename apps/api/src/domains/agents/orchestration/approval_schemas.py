"""
Schemas for the plan approval system (HITL Plan-Level).

This module defines the plan/step summary structures used to present
plans to the user (HITL question generation and streaming).
"""

from datetime import UTC, datetime
from typing import Any

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
        default_factory=lambda: datetime.now(UTC), description="Plan generation date"
    )
