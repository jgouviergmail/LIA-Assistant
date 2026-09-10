"""What a board read ASKS for, as statements nobody has executed yet (ADR-276).

Extracted from the repository when it crossed its size cap, and the cut is not
arbitrary: everything here is a pure ``select(...)`` — no session, no clock of
its own beyond ``now_utc`` — so it can be read, and tested, as a value. The
repository keeps what needs a session.

Two properties the extraction preserves, because they are the whole reason
these statements are shared rather than written per call site:

- **one visibility predicate**, applied by every read: a ticket is on U's board
  iff U owns it or holds it, and a second spelling would let one screen show
  what another hides;
- **one priority ranking**, read by the board's ordering AND by the heartbeat's
  nudge query — two copies would let them disagree about what matters most, and
  only one of the two is on screen for anyone to notice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, case, or_, select

from src.domains.workboard.constants import (
    CLOSED_STATUSES,
    AssigneeKind,
    TicketPriority,
    TicketStatus,
)
from src.domains.workboard.models import WorkboardTicket

#: Which holder a reader asked for. ``me`` covers both spellings of « I hold
#: it » — see :func:`apply_assignee`.
AssigneeFilter = Literal["me", "lia", "peer", "all"]

#: How a page comes back ordered.
SortKey = Literal["position", "priority", "due", "updated", "created"]

_PRIORITY_RANK: Final[dict[str, int]] = {
    TicketPriority.URGENT.value: 0,
    TicketPriority.HIGH.value: 1,
    TicketPriority.MEDIUM.value: 2,
    TicketPriority.LOW.value: 3,
}


def priority_rank() -> ColumnElement[int]:
    """The priority column as a sortable rank.

    Written once and read by both the board's ordering and the heartbeat's
    nudge query: a second copy would let the two disagree about which ticket
    matters most, and only one of them is on screen for anyone to notice.

    Returns:
        A SQL expression ranking urgent first and an unknown value last.
    """
    return case(_PRIORITY_RANK, value=WorkboardTicket.priority, else_=len(_PRIORITY_RANK))


@dataclass(frozen=True)
class BoardFilters:
    """What a board read asks for. The defaults read the whole board.

    Attributes:
        statuses: Columns to keep; None means every column.
        assignee: ``me`` (I hold it), ``lia``, ``peer`` (somebody else holds
            it), or ``all``.
        priorities: Priorities to keep; None means all four.
        overdue: Only tickets past their due date and still open.
        due_before: Only tickets due at or before this instant.
        query: Case-insensitive fragment of the title.
        include_closed_before: Hide closed tickets that closed BEFORE this
            instant. Never hides an open ticket, however old.
        sort: Which order the page comes back in.
    """

    statuses: tuple[str, ...] | None = None
    assignee: AssigneeFilter = "all"
    priorities: tuple[str, ...] | None = None
    overdue: bool = False
    due_before: datetime | None = None
    query: str | None = None
    include_closed_before: datetime | None = None
    sort: SortKey = "position"


def visible_predicate(user_id: UUID) -> ColumnElement[bool]:
    """A ticket is on this user's board iff they own it or hold it.

    Args:
        user_id: Whose board.

    Returns:
        The predicate every read applies.
    """
    return or_(
        WorkboardTicket.owner_user_id == user_id,
        WorkboardTicket.assignee_user_id == user_id,
    )


def apply_assignee(
    stmt: Select[tuple[WorkboardTicket]], user_id: UUID, assignee: AssigneeFilter
) -> Select[tuple[WorkboardTicket]]:
    """Narrow by who holds the ticket.

    ``me`` accepts both spellings of « I hold it »: my own id, and the NULL
    that means the owner does — a board where nothing was ever handed over
    stores NULL everywhere, and reading only the id would return nothing.
    ``peer`` is its complement among the held tickets: somebody else, never
    the reader.

    Args:
        stmt: The statement to narrow.
        user_id: The reader.
        assignee: Which holder the reader asked for.

    Returns:
        The narrowed statement.
    """
    if assignee == "me":
        return stmt.where(
            WorkboardTicket.assignee_kind == AssigneeKind.HUMAN.value,
            or_(
                WorkboardTicket.assignee_user_id == user_id,
                and_(
                    WorkboardTicket.assignee_user_id.is_(None),
                    WorkboardTicket.owner_user_id == user_id,
                ),
            ),
        )
    if assignee == "lia":
        return stmt.where(WorkboardTicket.assignee_kind == AssigneeKind.LIA.value)
    if assignee == "peer":
        # « Somebody ELSE holds it », and the reader is not somebody else. A
        # peer reads their own board too, and every ticket they hold carries
        # THEIR id here — so « held by anybody » handed them their own work
        # under a label saying a connection holds it, and « me » returned the
        # same rows. The two sides of the control are disjoint by shape.
        return stmt.where(
            WorkboardTicket.assignee_user_id.is_not(None),
            WorkboardTicket.assignee_user_id != user_id,
        )
    return stmt


def needs_me_stmt(user_id: UUID, now: datetime) -> Select[tuple[UUID]]:
    """The « needs me » set, as a statement its tests can read.

    Two situations, and only two: a run stopped and is waiting for THIS
    account — a question, or an action to confirm (lot 7) — or a ticket on this
    board is late.

    Args:
        user_id: The reader.
        now: The instant lateness is judged against.

    Returns:
        The id statement carrying the predicate.
    """
    return select(WorkboardTicket.id).where(
        and_(
            visible_predicate(user_id),
            or_(
                and_(
                    WorkboardTicket.status.in_(
                        (TicketStatus.WAITING.value, TicketStatus.CONFIRMING.value)
                    ),
                    or_(
                        WorkboardTicket.assignee_user_id == user_id,
                        and_(
                            WorkboardTicket.assignee_user_id.is_(None),
                            WorkboardTicket.owner_user_id == user_id,
                        ),
                    ),
                ),
                and_(
                    WorkboardTicket.due_at < now,
                    WorkboardTicket.status.not_in(tuple(sorted(CLOSED_STATUSES))),
                ),
            ),
        )
    )


__all__ = [
    "AssigneeFilter",
    "BoardFilters",
    "SortKey",
    "apply_assignee",
    "needs_me_stmt",
    "priority_rank",
    "visible_predicate",
]
