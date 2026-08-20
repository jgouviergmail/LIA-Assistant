"""Pydantic schemas for the Activity timeline (Lot 1-A1).

The API ships structured data only: the frontend resolves each ``kind``
to a localized label (``label_key`` doctrine — no pre-translated prose
in payloads).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ActivityEvent(BaseModel):
    """One proactive event surfaced on the timeline.

    ``text`` carries the human content already persisted by the source
    (notification content, reminder text, loop subject…); it is the user's
    own data returned to the authenticated owner, never a translated label.
    """

    kind: str = Field(description="Event kind (stable identifier, resolved to a label client-side)")
    ref_id: str = Field(description="Source row identifier (UUID as string)")
    occurred_at: datetime = Field(description="When the event happened (timezone-aware UTC)")
    text: str | None = Field(
        default=None,
        description="Main human content from the source row, if any (owner's own data)",
    )
    status: str | None = Field(
        default=None,
        description="Kind-specific qualifier (e.g. priority, closed_reason, habit status)",
    )


class ActivityKindTotal(BaseModel):
    """Exact windowed total for one event kind (ADR-185: exact or absent)."""

    kind: str = Field(description="Event kind the total refers to")
    total: int = Field(ge=0, description="Exact COUNT(*) over the whole window")
    truncated: bool = Field(
        description="True when the per-source cap dropped rows from the page pool"
    )


class ActivityTimelineResponse(BaseModel):
    """One page of the proactive activity timeline."""

    events: list[ActivityEvent] = Field(description="The requested page, newest first")
    totals: list[ActivityKindTotal] = Field(
        description="Exact per-kind totals over the window (failed sources are absent)"
    )
    has_more: bool = Field(description="True when rows exist beyond offset + limit")
    offset: int = Field(ge=0, description="Offset used for this page")
    limit: int = Field(ge=1, description="Page size used for this page")
    window_days: int = Field(ge=1, description="Look-back window of the aggregation")
    failed_kinds: list[str] = Field(
        default_factory=list,
        description="Kinds whose source failed — partial data is stated, never silent",
    )


class MergedTimeline(BaseModel):
    """Result of the pure merge: one page of events plus paging facts."""

    events: list[ActivityEvent] = Field(description="The requested page, newest first")
    has_more: bool = Field(description="True when rows exist beyond offset + limit")
    total_fetched: int = Field(
        description=(
            "Total merged rows available to pagination (fetched within the window, "
            "after per-source caps) — NOT the exact per-kind totals, which come "
            "from SQL aggregates (ADR-185)"
        )
    )
