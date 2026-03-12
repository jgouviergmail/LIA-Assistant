"""
HITL Unified Pydantic Schemas - Contracts for HITL payloads and responses.

This module defines Pydantic V2 schemas as source of truth for:
- HITL interrupt payloads (what triggers HITL)
- HITL response payloads (what user sends back)
- SSE chunk metadata (what frontend receives)

Benefits:
    - Type safety across frontend/backend boundary
    - Automatic validation of HITL data
    - Self-documenting API via schema export
    - Single source of truth for HITL contracts

Architecture:
    - HitlSeverity: Alert level for UI presentation
    - HitlAction: User response options
    - HitlInterruptPayload: Complete interrupt data
    - HitlUserResponse: User's decision payload

Design Patterns:
    - Discriminated Union: action_type as discriminator
    - Strict Mode: Pydantic V2 strict validation
    - Schema Export: JSON Schema generation for frontend

References:
    - protocols.py: HitlInteractionType enum
    - streaming/service.py: SSE chunk generation
    - Data Registry LOT 4: Registry ID integration

Created: 2026-01-11
Phase 2: HITL Consolidation
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class HitlSeverity(str, Enum):
    """
    Severity level for HITL interrupts.

    Determines UI presentation:
        - INFO: Standard confirmation (blue/neutral)
        - WARNING: Caution advised (yellow/orange)
        - CRITICAL: Destructive action (red)
    """

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class HitlActionStyle(str, Enum):
    """
    Button style for HITL action options.

    Maps to frontend component variants:
        - primary: Main action (confirm)
        - secondary: Alternative action (edit)
        - destructive: Dangerous action (delete, cancel)
        - ghost: Low-emphasis option
    """

    PRIMARY = "primary"
    SECONDARY = "secondary"
    DESTRUCTIVE = "destructive"
    GHOST = "ghost"


class HitlAction(BaseModel):
    """
    Single action option presented to user.

    Attributes:
        action: Machine-readable action identifier
        label: i18n key for button text
        style: Button visual style
        description: Optional tooltip/description
        keyboard_shortcut: Optional keyboard shortcut (e.g., "Enter", "Escape")
    """

    action: str = Field(..., description="Action identifier (e.g., 'confirm', 'cancel')")
    label: str = Field(..., description="i18n key or display text for button")
    style: HitlActionStyle = Field(default=HitlActionStyle.SECONDARY)
    description: str | None = Field(default=None, description="Optional tooltip")
    keyboard_shortcut: str | None = Field(default=None, description="Keyboard shortcut hint")


class HitlInterruptPayload(BaseModel):
    """
    Unified payload for all HITL interrupts.

    This is the canonical structure sent via SSE hitl_interrupt_metadata.
    Frontend uses this to render appropriate HITL UI.

    Attributes:
        message_id: Unique identifier for this HITL session
        conversation_id: Parent conversation UUID
        hitl_type: Type discriminator (plan_approval, draft_critique, etc.)
        available_actions: List of action options for user
        severity: Alert level for UI presentation
        context: Type-specific context data
        registry_ids: Data Registry IDs for rich rendering
        created_at: Timestamp for timeout tracking
    """

    message_id: str = Field(..., description="Unique HITL session identifier")
    conversation_id: str = Field(..., description="Parent conversation UUID")
    hitl_type: str = Field(..., description="Interaction type discriminator")
    available_actions: list[HitlAction] = Field(
        default_factory=list, description="Action options presented to user"
    )
    severity: HitlSeverity = Field(
        default=HitlSeverity.INFO, description="Alert level for UI styling"
    )
    context: dict[str, Any] = Field(default_factory=dict, description="Type-specific context data")
    registry_ids: list[str] = Field(
        default_factory=list, description="Data Registry IDs for rich card rendering"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Timestamp for timeout tracking"
    )

    # Draft-specific fields (populated when hitl_type == "draft_critique")
    draft_type: str | None = Field(default=None, description="Draft type (email, event, etc.)")
    draft_id: str | None = Field(default=None, description="Draft identifier")
    draft_content: dict[str, Any] | None = Field(default=None, description="Draft data preview")


class HitlUserResponse(BaseModel):
    """
    User's response to an HITL interrupt.

    Sent from frontend when user makes a decision.

    Attributes:
        message_id: HITL session identifier (must match interrupt)
        action: Selected action identifier
        modifications: Optional user modifications (for edit action)
        feedback: Optional user feedback/reason
    """

    message_id: str = Field(..., description="HITL session identifier")
    action: str = Field(..., description="Selected action (confirm, cancel, edit)")
    modifications: dict[str, Any] | None = Field(
        default=None, description="User modifications for edit action"
    )
    feedback: str | None = Field(
        default=None, description="Optional user feedback or cancellation reason"
    )


class DraftCritiqueContext(BaseModel):
    """
    Context for draft_critique HITL type.

    Structured data for draft review scenarios.
    """

    draft_type: str = Field(..., description="Type: email, event, contact, task, etc.")
    draft_id: str = Field(..., description="Unique draft identifier")
    draft_content: dict[str, Any] = Field(default_factory=dict, description="Draft data")
    draft_summary: str | None = Field(default=None, description="Pre-generated summary")


class ClarificationContext(BaseModel):
    """
    Context for clarification HITL type.

    Structured data for semantic validation clarifications.
    """

    clarification_questions: list[str] = Field(
        default_factory=list, description="Questions requiring user clarification"
    )
    semantic_issues: list[dict[str, Any]] = Field(
        default_factory=list, description="Detected semantic issues"
    )
    registry_ids: list[str] = Field(
        default_factory=list, description="Related registry items for context"
    )


class PlanApprovalContext(BaseModel):
    """
    Context for plan_approval HITL type.

    Structured data for execution plan review.
    """

    plan_summary: dict[str, Any] = Field(
        default_factory=dict, description="Plan summary for display"
    )
    planned_actions: list[dict[str, Any]] = Field(
        default_factory=list, description="List of planned operations"
    )
    approval_reasons: list[str] = Field(
        default_factory=list, description="Why approval is requested"
    )


class DestructiveConfirmContext(BaseModel):
    """
    Context for destructive_confirm HITL type.

    Enhanced confirmation for dangerous bulk operations.
    """

    operation_type: str = Field(..., description="Type of destructive operation")
    affected_count: int = Field(default=1, description="Number of items affected")
    affected_items: list[dict[str, Any]] = Field(
        default_factory=list, description="Preview of items to be affected"
    )
    warning_message: str = Field(
        default="This action cannot be undone.", description="Warning text for user"
    )
    require_confirmation_text: bool = Field(
        default=False, description="If True, user must type confirmation text"
    )
    confirmation_text: str | None = Field(
        default=None, description="Text user must type to confirm (e.g., 'DELETE')"
    )


class ForEachApprovalContext(BaseModel):
    """
    Context for for_each_approval HITL type (plan_planner.md Section 12).

    Enhanced confirmation for for_each iteration patterns that will
    execute an action N times (once per item in a collection).

    Use cases:
        - "Envoie un email à chaque contact" → 15 contacts = 15 emails
        - "Crée un rappel pour chaque rdv" → 8 events = 8 reminders
        - "Appelle la météo pour chaque ville" → 5 cities = 5 API calls

    UI presentation:
        - Shows total iteration count
        - Preview of items to iterate over
        - Estimated duration/cost
        - Option to limit iterations
    """

    iteration_count: int = Field(..., description="Number of items to iterate over")
    collection_key: str = Field(
        ..., description="Collection being iterated (contacts, events, etc.)"
    )
    action_description: str = Field(..., description="What will be done for each item")
    preview_items: list[dict[str, Any]] = Field(
        default_factory=list, description="Preview of first N items (max 5)"
    )
    for_each_max: int = Field(default=10, description="Current for_each_max limit")
    estimated_duration_seconds: float | None = Field(
        default=None, description="Estimated total duration"
    )
    original_step_id: str = Field(..., description="Original step ID before expansion")
    tool_name: str = Field(..., description="Tool that will be called for each item")


# Type alias for typed context (union of all context types)
# Allows dict[str, Any] for backwards compatibility, but prefer typed contexts
HitlContextType = (
    PlanApprovalContext
    | DraftCritiqueContext
    | DestructiveConfirmContext
    | ClarificationContext
    | ForEachApprovalContext
    | dict[str, Any]  # Fallback for unknown/legacy context types
)


# Standard action sets for common HITL types
STANDARD_DRAFT_ACTIONS = [
    HitlAction(
        action="confirm",
        label="confirm_and_execute",
        style=HitlActionStyle.PRIMARY,
        keyboard_shortcut="Enter",
    ),
    HitlAction(
        action="edit",
        label="edit_before_execute",
        style=HitlActionStyle.SECONDARY,
        keyboard_shortcut="E",
    ),
    HitlAction(
        action="cancel",
        label="cancel_operation",
        style=HitlActionStyle.DESTRUCTIVE,
        keyboard_shortcut="Escape",
    ),
]

STANDARD_PLAN_ACTIONS = [
    HitlAction(
        action="approve",
        label="approve_plan",
        style=HitlActionStyle.PRIMARY,
        keyboard_shortcut="Enter",
    ),
    HitlAction(
        action="reject",
        label="reject_plan",
        style=HitlActionStyle.DESTRUCTIVE,
        keyboard_shortcut="Escape",
    ),
]

STANDARD_DESTRUCTIVE_ACTIONS = [
    HitlAction(
        action="confirm_delete",
        label="confirm_deletion",
        style=HitlActionStyle.DESTRUCTIVE,
        keyboard_shortcut="Enter",
    ),
    HitlAction(
        action="cancel",
        label="keep_items",
        style=HitlActionStyle.SECONDARY,
        keyboard_shortcut="Escape",
    ),
]

STANDARD_FOR_EACH_ACTIONS = [
    HitlAction(
        action="confirm_all",
        label="execute_for_all",
        style=HitlActionStyle.PRIMARY,
        keyboard_shortcut="Enter",
        description="Execute action for all items in the collection",
    ),
    HitlAction(
        action="limit",
        label="limit_iterations",
        style=HitlActionStyle.SECONDARY,
        keyboard_shortcut="L",
        description="Reduce the number of iterations",
    ),
    HitlAction(
        action="cancel",
        label="cancel_iteration",
        style=HitlActionStyle.GHOST,
        keyboard_shortcut="Escape",
        description="Cancel the for_each operation",
    ),
]
