"""Pydantic schemas for the Open Loops API contract (P5, ADR-139)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
