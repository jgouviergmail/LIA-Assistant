"""Draft action request/result models.

Extracted from ``drafts/models.py`` (file-size ratchet — a logical file
never grows). One-way dependency: this module imports the enums and the
Draft model from ``models``; consumers import from here or via the
package ``__init__`` re-exports.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.domains.agents.drafts.models import Draft, DraftAction, DraftStatus


class DraftActionRequest(BaseModel):
    """
    User action request on a draft.

    Sent from frontend when user clicks confirm/edit/cancel.
    """

    draft_id: str = Field(..., description="ID of the draft")
    action: DraftAction = Field(..., description="Action to take")

    # For EDIT action: new content
    updated_content: dict[str, Any] | None = Field(
        default=None,
        description="Updated content (for EDIT action)",
    )

    # User context
    user_message: str | None = Field(
        default=None,
        description="Optional user message/feedback",
    )


class DraftActionResult(BaseModel):
    """
    Result of a draft action.

    Returned after processing a DraftActionRequest.
    """

    draft_id: str = Field(..., description="ID of the draft")
    action: DraftAction = Field(..., description="Action that was taken")
    success: bool = Field(..., description="Whether action succeeded")
    new_status: DraftStatus = Field(..., description="New draft status")

    # For CONFIRM action: execution result
    execution_result: dict[str, Any] | None = Field(
        default=None,
        description="Result of execution (for CONFIRM)",
    )

    # Error info
    error_message: str | None = Field(
        default=None,
        description="Error message if failed",
    )

    # Updated draft (for EDIT action)
    updated_draft: Draft | None = Field(
        default=None,
        description="Updated draft object (for EDIT)",
    )
