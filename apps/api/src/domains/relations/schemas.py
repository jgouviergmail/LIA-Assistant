"""Relations domain schemas (N-09) — the read-only CRM API contract.

All payloads are UI-ready and immutable. Timestamps are ISO-8601 UTC strings;
the frontend formats them in the user's timezone (briefing doctrine). Nothing
here is a source of truth — every field is aggregated from an existing domain,
and ``identity_confidence`` states how sure the name match is.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class IdentityConfidence(str, Enum):
    """How the relationship key was matched (honesty over false precision)."""

    EXACT = "exact"  # identical display name across sources
    NORMALIZED = "normalized"  # matched after accent/case folding


class RelationOpenLoop(BaseModel):
    """One open commitment involving this person."""

    model_config = ConfigDict(frozen=True)

    id: str
    subject: str
    direction: str = Field(description="user_owes | waiting_on_other")
    due_hint: datetime | None = None
    days_open: int = Field(ge=0)


class RelationCall(BaseModel):
    """One past call with this person (never the phone number — D-8)."""

    model_config = ConfigDict(frozen=True)

    id: str
    objective: str
    outcome: str | None = None
    summary: str | None = None
    created_at: datetime


class RelationMemory(BaseModel):
    """One stored memory mentioning this person."""

    model_config = ConfigDict(frozen=True)

    id: str
    content: str


class RelationSummary(BaseModel):
    """One row of the CRM overview — a person and why they surface now."""

    model_config = ConfigDict(frozen=True)

    display_name: str
    identity_confidence: IdentityConfidence
    open_loops_count: int = Field(ge=0)
    calls_count: int = Field(ge=0)
    # ISO-8601 UTC of the most recent signal (loop/call), for "last seen".
    last_interaction_at: datetime | None = None


class RelationsOverview(BaseModel):
    """The CRM overview — relationships ranked by recency of interaction."""

    model_config = ConfigDict(frozen=True)

    relations: list[RelationSummary]


class RelationDetail(BaseModel):
    """The 360° view of one relationship."""

    model_config = ConfigDict(frozen=True)

    display_name: str
    identity_confidence: IdentityConfidence
    open_loops: list[RelationOpenLoop]
    recent_calls: list[RelationCall]
    memories: list[RelationMemory]
