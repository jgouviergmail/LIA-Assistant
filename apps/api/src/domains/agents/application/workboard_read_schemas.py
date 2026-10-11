"""Source board filters and separately paged detail sections keep large histories bounded."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from src.domains.workboard.board_queries import AssigneeFilter, SortKey
from src.domains.workboard.constants import TicketPriority, TicketStatus
from src.domains.workboard.schemas import BoardSummary, CommentRow, EventRow, TicketRow

WorkboardReadSection = Literal[
    "board", "summary", "needs_me", "ticket", "children", "comments", "events"
]
DETAIL_SECTIONS = frozenset({"ticket", "children", "comments", "events"})


class WorkboardUIQuery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    section: WorkboardReadSection = "summary"
    ticket_id: UUID | None = None
    limit: StrictInt = Field(default=25, ge=1, le=50)
    offset: StrictInt = Field(default=0, ge=0)
    statuses: tuple[TicketStatus, ...] | None = Field(
        default=None, min_length=1, max_length=len(TicketStatus)
    )
    priorities: tuple[TicketPriority, ...] | None = Field(
        default=None, min_length=1, max_length=len(TicketPriority)
    )
    assignee: AssigneeFilter = "all"
    overdue: StrictBool = False
    due_before: datetime | None = None
    query: str | None = Field(default=None, max_length=200)
    closed_days: StrictInt | None = Field(default=None, ge=0, le=3650)
    sort: SortKey = "position"

    @model_validator(mode="after")
    def sections_accept_only_their_parameters(self) -> WorkboardUIQuery:
        if (self.section in DETAIL_SECTIONS) != (self.ticket_id is not None):
            raise ValueError(
                "A detail section requires its exact ticket ID; other sections take none"
            )
        board_fields = {
            "statuses",
            "priorities",
            "assignee",
            "overdue",
            "due_before",
            "query",
            "closed_days",
            "sort",
        }
        if self.section != "board" and self.model_fields_set & board_fields:
            raise ValueError("Board filters apply only to the board section")
        if self.due_before is not None and self.due_before.utcoffset() is None:
            raise ValueError("due_before requires an ISO instant with an explicit timezone")
        return self


class WorkboardUIProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section: WorkboardReadSection
    tickets: list[TicketRow] = Field(default_factory=list, max_length=50)
    ticket: TicketRow | None = None
    comments: list[CommentRow] = Field(default_factory=list, max_length=50)
    events: list[EventRow] = Field(default_factory=list, max_length=50)
    summary: BoardSummary | None = None
    total: int | None = Field(default=None, ge=0)
    counts_by_status: dict[str, int] = Field(default_factory=dict)
    next_offset: int | None = None
    observed_at: datetime
