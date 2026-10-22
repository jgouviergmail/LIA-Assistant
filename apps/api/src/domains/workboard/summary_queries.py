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

from sqlalchemy import Select, func, literal, select, union_all
from sqlalchemy.orm import aliased, load_only

from src.domains.workboard.board_queries import BoardFilters, needs_me_stmt
from src.domains.workboard.constants import OPEN_STATUSES
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
        held_by_me: Visible tickets this account holds — « my tickets ».
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
    held_by_me: int
    needs_me: int
    owned: int
    runs_total: int
    tokens_in: int
    tokens_out: int
    tokens_cache: int
    google_requests: int
    cost_eur: Decimal


@dataclass(frozen=True)
class AttentionFigures:
    """What on the board needs the person's attention — the dashboard card's read.

    Every figure counts OPEN tickets only: a finished ticket LIA held is not
    work LIA is doing, and the dashboard says what is in motion, where the
    settings summary describes the whole board.

    Attributes:
        needs_me: Tickets waiting on this account, or late on its board.
        held_by_me: Open tickets this account holds — « my tickets », never
            a ticket LIA or a peer holds, late or not (owner request 2026-10-21).
        held_by_lia: Open tickets LIA holds.
        held_by_peers: Open tickets another account holds (the board peer filter).
        overdue: Open tickets past their due date.
        open_total: Every open ticket on the visible board.
        needs_me_first: The legacy « needs me » page, earliest due first.
        previews: The first two rows in each exact counter's set, with overlaps
            preserved. Counts are aggregates, never derived from these pages.
    """

    needs_me: int
    held_by_me: int
    held_by_lia: int
    held_by_peers: int
    overdue: int
    open_total: int
    needs_me_first: list[WorkboardTicket]
    previews: dict[str, list[WorkboardTicket]]


async def read_attention(
    repo: WorkboardRepository, user_id: UUID, now: datetime, *, limit: int
) -> AttentionFigures:
    """Read what needs attention on the board, every figure an exact aggregate.

    Composed from the repository's own statements — the visibility predicate,
    the filters and the « needs me » set — so the dashboard card, the board and
    the hub can never disagree about what a figure means (ADR-185).

    Args:
        repo: The repository.
        user_id: Whose board.
        now: The instant lateness is judged against.
        limit: How many « needs me » tickets to return beside the counts.

    Returns:
        The counts and the first tickets waiting on the person.
    """
    db = repo.db
    counts = await repo.counts_by_status(user_id, BoardFilters())
    open_statuses = tuple(sorted(OPEN_STATUSES))
    lia_stmt = repo.filtered_stmt(user_id, BoardFilters(statuses=open_statuses, assignee="lia"))
    peer_stmt = repo.filtered_stmt(user_id, BoardFilters(statuses=open_statuses, assignee="peer"))
    me_stmt = repo.filtered_stmt(user_id, BoardFilters(statuses=open_statuses, assignee="me"))
    # Independent, possibly overlapping sets, in the same database round trip.
    holder_counts = select(
        count_over(lia_stmt).scalar_subquery(),
        count_over(peer_stmt).scalar_subquery(),
        count_over(me_stmt).scalar_subquery(),
    )
    held_by_lia, held_by_peers, held_by_me = (await db.execute(holder_counts)).one()
    overdue_tickets = repo.filtered_stmt(user_id, BoardFilters(overdue=True))
    overdue = int((await db.execute(count_over(overdue_tickets))).scalar() or 0)
    statements = {
        "needs_me": select(WorkboardTicket).where(
            WorkboardTicket.id.in_(needs_me_stmt(user_id, now))
        ),
        "held_by_me": me_stmt,
        "held_by_lia": lia_stmt,
        "held_by_peers": peer_stmt,
        "overdue": overdue_tickets,
        "open_total": repo.filtered_stmt(user_id, BoardFilters(statuses=open_statuses)),
    }
    groups: dict[str, list[WorkboardTicket]] = {key: [] for key in statements}
    for key, ticket in (await db.execute(_preview_stmt(statements, limit))).all():
        groups[key].append(ticket)
    needs_me = await repo.count_needs_me(user_id, now)
    return AttentionFigures(
        needs_me=needs_me,
        held_by_me=int(held_by_me),
        held_by_lia=int(held_by_lia),
        held_by_peers=int(held_by_peers),
        overdue=overdue,
        open_total=sum(counts.get(status, 0) for status in open_statuses),
        needs_me_first=groups["needs_me"][:limit],
        previews={key: tickets[:2] for key, tickets in groups.items()},
    )


def _preview_stmt(
    statements: dict[str, Select[tuple[WorkboardTicket]]], limit: int
) -> Select[tuple[str, WorkboardTicket]]:
    """Read bounded, possibly overlapping previews in one database round trip.

    The legacy needs-me page keeps its configured limit; the UI previews expose
    only two rows per group. Subqueries keep each LIMIT independent and portable.
    """
    parts = []
    for key, statement in statements.items():
        page = (
            statement.order_by(WorkboardTicket.due_at.asc().nulls_last(), WorkboardTicket.id.asc())
            .limit(max(limit, 2) if key == "needs_me" else 2)
            .subquery()
        )
        parts.append(select(literal(key).label("preview_group"), *page.c))
    combined = union_all(*parts).subquery()
    ticket = aliased(WorkboardTicket, combined)
    return (
        select(combined.c.preview_group, ticket)
        .options(load_only(ticket.id, ticket.title, ticket.status, ticket.due_at))
        .order_by(
            combined.c.preview_group, combined.c.due_at.asc().nulls_last(), combined.c.id.asc()
        )
    )


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
    me_stmt = count_over(repo.filtered_stmt(user_id, BoardFilters(assignee="me")))
    held_by_me = int((await db.execute(me_stmt)).scalar() or 0)
    needs_stmt = select(func.count()).select_from(needs_me_stmt(user_id, now).subquery())
    needs_me = int((await db.execute(needs_stmt)).scalar() or 0)
    owned, runs, tokens_in, tokens_out, tokens_cache, google, cost = (
        await db.execute(owned_totals_stmt(user_id))
    ).one()
    return BoardSummaryFigures(
        counts_by_status=counts,
        overdue=overdue,
        held_by_lia=held_by_lia,
        held_by_me=held_by_me,
        needs_me=needs_me,
        owned=int(owned),
        runs_total=int(runs),
        tokens_in=int(tokens_in),
        tokens_out=int(tokens_out),
        tokens_cache=int(tokens_cache),
        google_requests=int(google),
        cost_eur=Decimal(cost),
    )
