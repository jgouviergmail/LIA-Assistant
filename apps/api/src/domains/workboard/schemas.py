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
    category_id: UUID | None = Field(
        default=None,
        description=(
            "One of the caller's OWN categories — the board lane to file it under. "
            "Omitted, a step takes its parent's and any other ticket stays unfiled."
        ),
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
    category_id: UUID | None = Field(
        default=None,
        description="File it under this category of the owner's (owner only); absent leaves it.",
    )
    clear_category: bool = Field(
        default=False, description="Take it out of its category (owner only)."
    )

    @model_validator(mode="before")
    @classmethod
    def explicit_null_returns_to_owner(cls, value: object) -> object:
        """The UI's explicit null holder means return to the owner; absent stays unchanged."""
        if (
            isinstance(value, dict)
            and "assignee_user_id" in value
            and value["assignee_user_id"] is None
            and value.get("assignee") is None
        ):
            return {**value, "assignee": "me"}
        return value

    @model_validator(mode="after")
    def a_date_is_set_or_cleared_never_both(self) -> TicketUpdate:
        """Refuse setting and clearing the same date in one request.

        Returns:
            The validated request.

        Raises:
            ValueError: When a date or the category arrives beside its own
                clear flag, or when two ways of naming the holder arrive together.
        """
        if self.clear_start_at and self.start_at is not None:
            raise ValueError("send either start_at or clear_start_at, not both")
        if self.clear_due_at and self.due_at is not None:
            raise ValueError("send either due_at or clear_due_at, not both")
        if self.assignee is not None and self.assignee_user_id is not None:
            raise ValueError("send either assignee (me | lia) or assignee_user_id, not both")
        _one_category_instruction(self.category_id, self.clear_category)
        return self


def _one_category_instruction(category_id: UUID | None, clear_category: bool) -> None:
    """Refuse filing a ticket and un-filing it in one request.

    The category has the dates' three states — set it, leave it, remove it —
    and ``None`` already means « leave it », so removing is explicit.

    Args:
        category_id: The category to file under, or None.
        clear_category: Whether to take the ticket out of its category.

    Raises:
        ValueError: When both arrive together.
    """
    if clear_category and category_id is not None:
        raise ValueError("send either category_id or clear_category, not both")


class CommentCreate(BaseModel):
    """One comment. Plain text — no attachments in this version."""

    model_config = ConfigDict(extra="forbid")

    body: str = Field(description="Plain text.")


class MoveRequest(BaseModel):
    """The drag-and-drop write: which column, where in it — and which lane.

    A drag across two lanes changes the column AND the category in one gesture,
    so it is one write: two requests would leave the card in a place nobody
    put it for as long as the second one took. The lane is optional, and a move
    that says nothing about it leaves the ticket filed where it was.
    """

    model_config = ConfigDict(extra="forbid")

    status: str = Field(description="The column to move into.")
    position: int = Field(ge=0, description="Index within the column, 0 first.")
    category_id: UUID | None = Field(
        default=None, description="The lane it lands in (owner only); absent leaves it."
    )
    clear_category: bool = Field(
        default=False, description="It lands in the unfiled lane (owner only)."
    )

    @model_validator(mode="after")
    def a_lane_is_set_or_cleared_never_both(self) -> MoveRequest:
        """Refuse two destinations for one drop.

        Returns:
            The validated request.

        Raises:
            ValueError: When a category arrives beside ``clear_category``.
        """
        _one_category_instruction(self.category_id, self.clear_category)
        return self


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
    #: The chat meter's two other figures for the same run; None on a run
    #: settled before they were kept whose ledger no longer says.
    last_run_tokens_cache: int | None
    last_run_google_requests: int | None
    last_run_cost_eur: float | None
    #: What the ticket has cost SINCE IT WAS CREATED, in the vocabulary the chat
    #: already shows. A ticket is run up to ten times, and « what did this cost
    #: me » is a question about the ticket, not about its last minute.
    total_tokens_in: int
    total_tokens_out: int
    total_tokens_cache: int
    total_google_requests: int
    total_cost_eur: float
    #: The OWNER's category, by id: the name travels with the board's lanes and
    #: the category list, never on every row.
    category_id: UUID | None
    created_at: datetime
    updated_at: datetime


class LaneRow(BaseModel):
    """One lane of the board: a category, and its exact count per column.

    ``category_id`` is None for the lane of tickets filed under nothing. A lane
    whose ``owner_user_id`` is not the reader is somebody else's category, on
    the reader's board because they hold a ticket filed under it: they read it,
    and cannot manage it.
    """

    category_id: UUID | None = Field(description="The category; None for the unfiled lane.")
    name: str | None = Field(description="The category's name; None for the unfiled lane.")
    owner_user_id: UUID | None = Field(description="Whose category; None for the unfiled lane.")
    counts_by_status: dict[str, int] = Field(
        description="Exact count per column over the page's own filter, all columns."
    )


class BoardPage(BaseModel):
    """A page of the board, the EXACT total, and one exact count per column.

    The counts come from an aggregate over the page's own filter (ADR-185): a
    column header disagreeing with the column under it is worse than no header.
    Every declared column is present, zero-filled — a missing key would read as
    « there is no such column » rather than « nothing is in it ».

    ``lanes`` is EMPTY for a reader with no category in sight: the board then
    draws what it drew before categories existed. Otherwise it leads with the
    unfiled lane, then the reader's own categories in their order, then the
    categories of the tickets they hold for somebody else.
    """

    tickets: list[TicketRow]
    total: int = Field(ge=0, description="Exact number of tickets the filter matches.")
    counts_by_status: dict[str, int] = Field(description="Exact count per column, all columns.")
    lanes: list[LaneRow] = Field(description="The board's lanes, in display order; may be empty.")


class CategoryCreate(BaseModel):
    """A new category. The name's bound is the service's, read from settings."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="What the lane is called.")
    position: int | None = Field(
        default=None, ge=0, description="Index among the caller's categories; omitted appends."
    )


class CategoryUpdate(BaseModel):
    """A partial update of a category: its name, its place, or both."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, description="A new name.")
    position: int | None = Field(
        default=None, ge=0, description="A new index among the caller's categories."
    )

    @model_validator(mode="after")
    def something_changes(self) -> CategoryUpdate:
        """Refuse a patch that names nothing.

        Returns:
            The validated request.

        Raises:
            ValueError: When neither a name nor a position arrives.
        """
        if self.name is None and self.position is None:
            raise ValueError("send a name, a position, or both")
        return self


class CategoryRow(BaseModel):
    """One category as the board's lists read it."""

    id: UUID
    owner_user_id: UUID
    name: str
    position: int = Field(ge=0, description="Order among its owner's categories.")
    ticket_count: int = Field(
        ge=0, description="Exact number of tickets on the READER's board filed under it."
    )


class CategoryList(BaseModel):
    """Every category on the reader's board, and the caps the instance enforces.

    Their own first, in their order; then the categories of the tickets they
    hold for somebody else. The caps travel with the list (ADR-184): a bound
    the form cannot read is a bound the person walks into.
    """

    categories: list[CategoryRow]
    max_categories: int = Field(ge=1, description="Categories an account may define (setting).")
    name_max_chars: int = Field(ge=1, description="Longest name accepted (setting).")


class CategoryDeleteResult(BaseModel):
    """What deleting a category did to the tickets filed under it."""

    released: int = Field(ge=0, description="Tickets sent back to the unfiled lane.")


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
    as_of: datetime | None = Field(None, description="Server-bounded upper creation instant.")
    total: int = Field(ge=0)
    categories: dict[UUID, str] = Field(
        default_factory=dict,
        description=(
            "Name of every category a ticket of THIS page is filed under, by id. "
            "The board draws a lane; off the board the lane is a badge."
        ),
    )


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
    held_by_me: int = Field(ge=0, description="Visible tickets the caller holds.")
    needs_me: int = Field(
        ge=0, description="Tickets waiting on the caller, or late on their board."
    )
    lanes: list[LaneRow] = Field(
        default_factory=list,
        description=(
            "Exact count per category and per column over the WHOLE visible board, "
            "the unfiled lane first. Empty for a reader with no category in sight."
        ),
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
