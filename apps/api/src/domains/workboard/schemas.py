"""Workboard API contract (ADR-276).

Bounds are deliberately NOT repeated here as literals. The service enforces
them from settings and the agent manifests (lot 3) publish the SAME settings,
so a ``max_length`` typed by hand would be a second authority — right until an
operator retunes the setting, after which it refuses what the service accepts
(ADR-184's trap, pointing the other way).

What Pydantic DOES own here is shape: which fields exist, which combinations
are refusable without knowing any deployment's numbers, and the difference
between « leave this alone » and « clear it ».
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.core.constants import OUT_OF_TURN_EXECUTION_MODE_DEFAULT, ExecutionMode

#: How the caller names an assignment that stays inside their own account.
#: A peer is named by id instead (``assignee_user_id``), because a name is
#: resolved against the accepted connections and that resolution belongs to
#: the caller's own client, never to a free string on the wire.
AssigneeRef = Literal["me", "lia"]


class TicketCreate(BaseModel):
    """What a creation carries.

    ``assignee`` names the owner's own hands or their LIA; ``assignee_user_id``
    names a connected peer. Sending both is refused rather than resolved: they
    can disagree, and the ticket would then be filed against one holder while
    the reader was told another.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(description="What the ticket is.")
    description: str | None = Field(
        default=None, description="The brief LIA runs when assigned; the owner's words."
    )
    priority: str = Field(default="medium", description="low | medium | high | urgent")
    status: str = Field(default="todo", description="The column to create it in.")
    start_at: datetime | None = Field(default=None, description="UTC instant work may start.")
    due_at: datetime | None = Field(default=None, description="UTC instant it is due.")
    assignee: AssigneeRef = Field(default="me", description="me | lia")
    assignee_user_id: UUID | None = Field(
        default=None, description="A CONNECTED peer's account id."
    )
    parent_id: UUID | None = Field(default=None, description="Parent ticket (one level only).")
    execution_mode: ExecutionMode = Field(
        default=OUT_OF_TURN_EXECUTION_MODE_DEFAULT,
        description="How LIA runs it: react (autonomous loop) or pipeline.",
    )
    follow: bool = Field(
        default=False, description="Notify me in the chat about what happens on this ticket."
    )

    @model_validator(mode="after")
    def one_way_to_name_the_holder(self) -> TicketCreate:
        """Refuse two ways of saying who holds the ticket.

        Returns:
            The validated request.

        Raises:
            ValueError: When a peer id arrives beside an explicit ``assignee``.
        """
        if self.assignee_user_id is not None and self.assignee != "me":
            raise ValueError("send either assignee (me | lia) or assignee_user_id, not both")
        return self


class TicketUpdate(BaseModel):
    """A partial update: absent means unchanged.

    Dates need a third state — « set it », « leave it » and « clear it » — and
    ``None`` already means « leave it » here, so clearing is explicit
    (``clear_start_at`` / ``clear_due_at``). Without that, a caller could never
    remove a due date once set.

    **``parent_id`` is deliberately absent.** A ticket's place in the hierarchy
    is fixed at creation: re-parenting needs the depth rule AND a cycle check
    that creation cannot need (a new ticket has no descendants), and nothing
    has asked for it. Adding the field without both checks would let a caller
    make two tickets each other's parent.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    description: str | None = None
    priority: str | None = None
    status: str | None = None
    start_at: datetime | None = None
    due_at: datetime | None = None
    clear_start_at: bool = Field(default=False, description="Remove the start date.")
    clear_due_at: bool = Field(default=False, description="Remove the due date.")
    assignee: AssigneeRef | None = None
    assignee_user_id: UUID | None = None
    execution_mode: ExecutionMode | None = Field(
        default=None,
        description="Changeable at any point of the ticket's life; the next run reads it.",
    )
    follow: bool | None = Field(
        default=None, description="The CALLER's own follow flag, never the other side's."
    )

    @model_validator(mode="after")
    def a_date_is_set_or_cleared_never_both(self) -> TicketUpdate:
        """Refuse setting and clearing the same date in one request.

        Returns:
            The validated request.

        Raises:
            ValueError: When a date arrives beside its own clear flag, or when
                two ways of naming the holder arrive together.
        """
        if self.clear_start_at and self.start_at is not None:
            raise ValueError("send either start_at or clear_start_at, not both")
        if self.clear_due_at and self.due_at is not None:
            raise ValueError("send either due_at or clear_due_at, not both")
        if self.assignee is not None and self.assignee_user_id is not None:
            raise ValueError("send either assignee (me | lia) or assignee_user_id, not both")
        return self


class CommentCreate(BaseModel):
    """One comment. Plain text — no attachments in this version."""

    model_config = ConfigDict(extra="forbid")

    body: str = Field(description="Plain text.")


class MoveRequest(BaseModel):
    """The drag-and-drop write: which column, and where in it."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(description="The column to move into.")
    position: int = Field(ge=0, description="Index within the column, 0 first.")


class TicketRow(BaseModel):
    """One ticket, as the board and the detail panel read it.

    ``assignee_user_id`` is the STORED value: NULL means the owner holds it.
    ``effective_assignee_id`` resolves that convention once, server-side, so no
    client re-implements it.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_user_id: UUID
    parent_id: UUID | None
    title: str
    description: str | None
    status: str
    priority: str
    start_at: datetime | None
    due_at: datetime | None
    assignee_kind: str
    assignee_user_id: UUID | None
    effective_assignee_id: UUID
    position: int
    follow_owner: bool
    follow_assignee: bool
    created_by: str
    execution_mode: str
    status_changed_at: datetime
    run_count: int
    #: Set while a run is IN FLIGHT, cleared when it settles. The only
    #: honest signal of « LIA is working on it »: a failed run leaves the
    #: ticket in `in_progress`, so the column cannot say it.
    run_claimed_at: datetime | None
    last_run_at: datetime | None
    last_run_outcome: str | None
    last_run_error: str | None
    last_run_tokens_in: int | None
    last_run_tokens_out: int | None
    last_run_cost_eur: float | None
    #: What the ticket has cost SINCE IT WAS CREATED, in the vocabulary the chat
    #: already shows. A ticket is run up to ten times, and « what did this cost
    #: me » is a question about the ticket, not about its last minute.
    total_tokens_in: int
    total_tokens_out: int
    total_tokens_cache: int
    total_google_requests: int
    total_cost_eur: float
    created_at: datetime
    updated_at: datetime


class BoardPage(BaseModel):
    """A page of the board, the EXACT total, and one exact count per column.

    The counts come from an aggregate over the page's own filter (ADR-185): a
    column header disagreeing with the column under it is worse than no header.
    Every declared column is present, zero-filled — a missing key would read as
    « there is no such column » rather than « nothing is in it ».
    """

    tickets: list[TicketRow]
    total: int = Field(ge=0, description="Exact number of tickets the filter matches.")
    counts_by_status: dict[str, int] = Field(description="Exact count per column, all columns.")


class CommentRow(BaseModel):
    """One comment as the detail panel reads it."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    author_kind: str
    author_user_id: UUID | None
    body: str
    run_id: str | None
    created_at: datetime


class EventRow(BaseModel):
    """One history entry as the detail panel reads it."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_kind: str
    actor_user_id: UUID | None
    kind: str
    payload: dict[str, object] | None
    created_at: datetime


class TicketDetail(BaseModel):
    """A ticket with everything its detail panel shows."""

    ticket: TicketRow
    children: list[TicketRow]
    comments: list[CommentRow]
    events: list[EventRow]


class DeleteResult(BaseModel):
    """What a deletion actually removed, children included."""

    removed: int = Field(ge=1, description="Rows removed, the ticket and its children.")


class NeedsMePage(BaseModel):
    """Tickets waiting on the caller, and the exact total behind the page."""

    tickets: list[TicketRow]
    total: int = Field(ge=0)


class BoardSummary(BaseModel):
    """The board at a glance (lot 18).

    Every figure is an aggregate over its WHOLE set (ADR-185), never the length
    of a page, and the caps the instance enforces travel with it (ADR-184):
    a bound the settings page cannot read is a bound it cannot show.
    """

    total: int = Field(ge=0, description="Visible tickets — owned or held.")
    counts_by_status: dict[str, int] = Field(description="Exact count per column, all columns.")
    overdue: int = Field(ge=0, description="Open tickets past their due date.")
    held_by_lia: int = Field(ge=0, description="Visible tickets LIA holds.")
    needs_me: int = Field(
        ge=0, description="Tickets waiting on the caller, or late on their board."
    )
    owned: int = Field(ge=0, description="Tickets the caller owns — what the cap counts.")
    max_tickets: int = Field(ge=1, description="Tickets an account may own (runtime setting).")
    max_runs_per_ticket: int = Field(ge=1, description="Runs a ticket may take (runtime setting).")
    runs_total: int = Field(ge=0, description="Runs over the owned tickets, summed.")
    tokens_in: int = Field(ge=0, description="Input tokens the owned tickets spent.")
    tokens_out: int = Field(ge=0, description="Output tokens the owned tickets spent.")
    tokens_cache: int = Field(ge=0, description="Cached tokens the owned tickets spent.")
    google_requests: int = Field(ge=0, description="Google API requests, summed.")
    cost_eur: float = Field(ge=0, description="What the owned tickets have cost, in euros.")
