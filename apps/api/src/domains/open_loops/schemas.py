"""Pydantic schemas for the Open Loops API contract (P5, ADR-139)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CloseLoopRequest(BaseModel):
    """Optional close payload (UXR Lot 7, B5).

    ``done`` maps to closed_reason "api" (the historical value), ``dismissed``
    records "no longer relevant". ``conversational``/``expired`` are never
    accepted from the API — they belong to the extractor and the lazy expiry.
    """

    model_config = ConfigDict(frozen=True)

    action: Literal["done", "dismissed"] = Field(
        default="done",
        description=(
            "Why the user closes the loop: done (completed) | dismissed " "(no longer relevant)."
        ),
    )


class UpdateLoopRequest(BaseModel):
    """Correction of a commitment the extractor read wrong (2026-08-02).

    Only the two fields conversation gets wrong are editable. ``direction`` and
    ``counterparty`` are not: changing them does not correct this commitment, it
    describes another one — and the ledger's value is that it reflects what was
    actually said.

    ``clear_due_hint`` exists because ``None`` cannot mean two things at once:
    omitting ``due_hint`` leaves the deadline alone, while this flag says "there
    is no deadline after all".
    """

    model_config = ConfigDict(frozen=True)

    subject: str | None = Field(
        default=None,
        min_length=1,
        max_length=500,
        description="Corrected wording of the commitment.",
    )
    due_hint: datetime | None = Field(
        default=None,
        description="Corrected advisory deadline (UTC). Omit to leave unchanged.",
    )
    clear_due_hint: bool = Field(
        default=False,
        description="Drop the deadline entirely (wins over due_hint).",
    )

    @field_validator("subject")
    @classmethod
    def _reject_blank_subject(cls, value: str | None) -> str | None:
        """A commitment with no wording says nothing to anyone.

        Args:
            value: Candidate subject.

        Returns:
            The trimmed subject, or None when the field was omitted.

        Raises:
            ValueError: The subject was whitespace only.
        """
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("subject cannot be blank")
        return trimmed


class OpenLoopResponse(BaseModel):
    """One tracked commitment, as returned by the API."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    subject: str = Field(description="What the commitment is about")
    counterparty: str | None = Field(default=None, description="Other side of the loop")
    direction: str = Field(description="user_owes | waiting_on_other")
    due_hint: datetime | None = Field(default=None, description="Advisory deadline (UTC)")
    status: str = Field(description="open | closed | expired")
    closed_reason: str | None = Field(default=None, description="Why the loop left OPEN")
    nudge_count: int = Field(description="How many notifications surfaced this loop")
    created_at: datetime
    updated_at: datetime


class OpenLoopListResponse(BaseModel):
    """List envelope for the open-loops listing."""

    model_config = ConfigDict(frozen=True)

    items: list[OpenLoopResponse]
    total: int = Field(description="Number of returned loops")
