"""Schemas for the platform capability switches.

Created: 2026-08-06 (live-demonstrator programme, lot 3)
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CapabilitySwitchResponse(BaseModel):
    """One capability, as an administrator sees it.

    ``switch_enabled`` is what the operator set; ``deployment_available`` is
    what the environment allows; ``effective_enabled`` is what the runtime
    actually enforces. Showing only the first would let an operator flip a
    switch that changes nothing.
    """

    capability: str = Field(description="Stable capability identifier")
    label_key: str = Field(description="i18n key for the human-readable label")
    switch_enabled: bool = Field(description="The operator switch, as stored")
    deployment_available: bool = Field(
        description="Whether the deployment (environment) permits this capability at all"
    )
    effective_enabled: bool = Field(description="What the runtime enforces: switch AND deployment")
    enforced_in_catalogue: bool = Field(
        default=False,
        description="Whether disabling it removes tools from the planner catalogue",
    )
    enforced_on_routes: bool = Field(
        default=False,
        description="Whether disabling it makes routes or the voice pipeline refuse",
    )
    updated_by: UUID | None = Field(default=None, description="Admin who last flipped this switch")
    updated_at: datetime | None = Field(
        default=None, description="When the switch was last flipped"
    )
    is_default: bool = Field(default=False, description="True when no operator value is stored")

    model_config = {"from_attributes": True}


class CapabilitySwitchUpdate(BaseModel):
    """Request to flip one capability switch."""

    enabled: bool = Field(description="Whether the capability should be offered")
    change_reason: str | None = Field(
        default=None,
        max_length=500,
        description="Optional reason for the change (for audit trail)",
    )
