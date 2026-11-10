"""Pydantic schemas for the Activity timeline (Lot 1-A1).

The API ships structured data only: the frontend resolves each ``kind``
to a localized label (``label_key`` doctrine — no pre-translated prose
in payloads).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from src.core.constants import ACTIVITY_TIMELINE_PAGE_SIZE_MAX, DISPLAY_SEARCH_MAX_LENGTH
from src.domains.activity.constants import ALL_ACTIVITY_KINDS


class ActivityCriteria(BaseModel):
    """One immutable filter and time boundary shared by every selected source."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    q: str = Field(
        default="", max_length=DISPLAY_SEARCH_MAX_LENGTH, description="Literal displayed text"
    )
    kinds: tuple[str, ...] = Field(
        default=(),
        max_length=len(ALL_ACTIVITY_KINDS),
        description="Selected kinds; empty means all",
    )
    sort: Literal["recent", "oldest"] = Field(
        default="recent", description="Chronological direction"
    )
    as_of: AwareDatetime | None = Field(
        default=None, description="Upper instant; the server supplies the first page's bound"
    )

    @field_validator("kinds")
    @classmethod
    def validate_kinds(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """The producer registry owns the vocabulary; publish one canonical order."""
        if set(value) - set(ALL_ACTIVITY_KINDS):
            raise ValueError("Unknown activity kind")
        return tuple(kind for kind in ALL_ACTIVITY_KINDS if kind in value)


class ActivityTimelineQuery(ActivityCriteria):
    """The public read contract; page size stays bounded independently of sources."""

    offset: int = Field(default=0, ge=0, description="Rows to skip in the complete ordered prefix")
    limit: int | None = Field(
        default=None,
        ge=1,
        le=ACTIVITY_TIMELINE_PAGE_SIZE_MAX,
        description="Page size; absent uses the configured default",
    )


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
    total: int = Field(ge=0, description="Exact matching count over the whole owned window")
    truncated: bool = Field(
        description="True when the per-source cap dropped rows from the page pool"
    )


class ActivityTimelineResponse(BaseModel):
    """One page of the proactive activity timeline."""

    events: list[ActivityEvent] = Field(description="The requested page in the applied order")
    criteria: ActivityCriteria = Field(
        description="Applied filter with the server's stable upper instant"
    )
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

    events: list[ActivityEvent] = Field(description="The requested page in the applied order")
    has_more: bool = Field(description="True when rows exist beyond offset + limit")
    total_fetched: int = Field(
        description=(
            "Total merged rows available to pagination (fetched within the window, "
            "after per-source caps) — NOT the exact per-kind totals, which come "
            "from complete source reads (ADR-185)"
        )
    )
