"""The board at a glance — every figure an aggregate over its WHOLE set (ADR-276, lot 18).

The settings section used to be a sentence and a button. It now shows what the
board holds — per column, late, held by LIA, waiting on the person — what the
account owns against the instance's cap, and what its tickets have cost. Each
of those is a COUNT or a SUM over the whole set, never the length of a page
(ADR-185): a page the reader never asked for cannot describe a board.

Beside the repository rather than inside it: the repository file sits under
the logical-SLOC cap, and these statements are the summary's alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Select, func, select

from src.domains.workboard.board_queries import BoardFilters, needs_me_stmt
from src.domains.workboard.models import WorkboardTicket

if TYPE_CHECKING:
    from src.domains.workboard.repository import WorkboardRepository


@dataclass(frozen=True)
class BoardSummaryFigures:
    """The board at a glance.

    Attributes:
        counts_by_status: One exact count per column, over everything visible.
        overdue: Open tickets past their due date, on the visible board.
        held_by_lia: Visible tickets LIA holds.
        needs_me: Tickets waiting on this account, or late on its board.
        owned: Tickets this account owns — what the cap counts.
        runs_total: Runs over the owned tickets, summed.
        tokens_in: Input tokens the owned tickets have spent, summed.
        tokens_out: Output tokens, summed.
        tokens_cache: Cached tokens, summed.
        google_requests: Google API requests, summed.
        cost_eur: What the owned tickets have cost, in euros.
    """

    counts_by_status: dict[str, int]
    overdue: int
    held_by_lia: int
    needs_me: int
    owned: int
    runs_total: int
    tokens_in: int
    tokens_out: int
    tokens_cache: int
    google_requests: int
    cost_eur: Decimal


def count_over(stmt: Select[tuple[WorkboardTicket]]) -> Select[tuple[int]]:
    """The exact size of a filtered set — a count over the SAME statement.

    Args:
        stmt: A filtered, possibly ordered, statement over the tickets.

    Returns:
        The count statement.
    """
    return select(func.count()).select_from(stmt.order_by(None).subquery())


def owned_totals_stmt(user_id: UUID) -> Select[tuple[int, int, int, int, int, int, Decimal]]:
    """What this account OWNS, and what it has spent, in one aggregate.

    The spend is summed over the tickets the account OWNS, never over what it
    merely holds: a run works with the owner's tools and is billed to them
    (ADR-276, « a ticket's spend is the account's »).

    Args:
        user_id: The owner.

    Returns:
        count, runs, tokens in, tokens out, tokens cached, Google requests,
        cost — every sum zero-filled, so an empty board reads as zeros.
    """
    return select(
        func.count(),
        func.coalesce(func.sum(WorkboardTicket.run_count), 0),
        func.coalesce(func.sum(WorkboardTicket.total_tokens_in), 0),
        func.coalesce(func.sum(WorkboardTicket.total_tokens_out), 0),
        func.coalesce(func.sum(WorkboardTicket.total_tokens_cache), 0),
        func.coalesce(func.sum(WorkboardTicket.total_google_requests), 0),
        func.coalesce(func.sum(WorkboardTicket.total_cost_eur), 0),
    ).where(WorkboardTicket.owner_user_id == user_id)


async def read_board_summary(
    repo: WorkboardRepository, user_id: UUID, now: datetime
) -> BoardSummaryFigures:
    """Read the board at a glance.

    Args:
        repo: The repository — the one visibility predicate and filter.
        user_id: Whose board.
        now: The instant lateness is judged against.

    Returns:
        Every figure an aggregate over its whole set.
    """
    db = repo.db
    counts = await repo.counts_by_status(user_id, BoardFilters())
    overdue_stmt = count_over(repo.filtered_stmt(user_id, BoardFilters(overdue=True)))
    overdue = int((await db.execute(overdue_stmt)).scalar() or 0)
    lia_stmt = count_over(repo.filtered_stmt(user_id, BoardFilters(assignee="lia")))
    held_by_lia = int((await db.execute(lia_stmt)).scalar() or 0)
    needs_stmt = select(func.count()).select_from(needs_me_stmt(user_id, now).subquery())
    needs_me = int((await db.execute(needs_stmt)).scalar() or 0)
    owned, runs, tokens_in, tokens_out, tokens_cache, google, cost = (
        await db.execute(owned_totals_stmt(user_id))
    ).one()
    return BoardSummaryFigures(
        counts_by_status=counts,
        overdue=overdue,
        held_by_lia=held_by_lia,
        needs_me=needs_me,
        owned=int(owned),
        runs_total=int(runs),
        tokens_in=int(tokens_in),
        tokens_out=int(tokens_out),
        tokens_cache=int(tokens_cache),
        google_requests=int(google),
        cost_eur=Decimal(cost),
    )
