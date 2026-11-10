"""The Workboard card: what on the person's board needs them (ADR-276).

A local read beside the provider cards of ``fetchers.py``, with the same contract:
a populated ``WorkboardData``, or ``ConnectorNotConfiguredError`` when the instance
switched the workboard off — read at call time (ADR-280). Its own session, opened
through ``get_db_context()`` and closed before returning, because the briefing
gathers its fetchers in parallel and an ``AsyncSession`` is never shared across
concurrent tasks.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from src.core.config import settings
from src.core.time_utils import now_utc
from src.domains.briefing.exceptions import ConnectorNotConfiguredError
from src.domains.briefing.schemas import WorkboardData, WorkboardPreviews, WorkboardTicketItem
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.workboard.constants import CLOSED_STATUSES
from src.domains.workboard.models import WorkboardTicket
from src.domains.workboard.repository import WorkboardRepository
from src.domains.workboard.summary_queries import read_attention
from src.infrastructure.database.session import get_db_context


async def fetch_workboard(*, user_id: UUID) -> WorkboardData:
    """What on the person's workboard needs their attention.

    Exact aggregates over the whole board (ADR-185) — waiting on them, held by
    them, by LIA, by peers, late, open — plus the first tickets waiting on them.
    The workboard's own statements keep the card, board and hub in agreement
    on every figure. A local read: one session, closed before returning.

    Args:
        user_id: Whose board.

    Returns:
        The card's figures and its first tickets.

    Raises:
        ConnectorNotConfiguredError: when the instance switched the workboard
            off — read AT CALL TIME, so a switch flipped after boot hides the
            card on the next load (ADR-280).
    """
    if not await is_capability_enabled(PlatformCapability.WORKBOARD):
        raise ConnectorNotConfiguredError("workboard")
    now = now_utc()
    async with get_db_context() as db:
        figures = await read_attention(
            WorkboardRepository(db),
            user_id,
            now,
            limit=settings.briefing_max_workboard_items,
        )
        items = [_workboard_item(ticket, now) for ticket in figures.needs_me_first]
        previews = WorkboardPreviews.model_validate(
            {
                key: [_workboard_item(ticket, now) for ticket in tickets]
                for key, tickets in figures.previews.items()
            }
        )
    return WorkboardData(
        needs_me=figures.needs_me,
        held_by_me=figures.held_by_me,
        held_by_lia=figures.held_by_lia,
        held_by_peers=figures.held_by_peers,
        overdue=figures.overdue,
        open_total=figures.open_total,
        items=items,
        previews=previews,
    )


def _workboard_item(ticket: WorkboardTicket, now: datetime) -> WorkboardTicketItem:
    """The same read-only ticket projection for legacy rows and grouped previews."""
    return WorkboardTicketItem(
        id=str(ticket.id),
        title=ticket.title,
        status=ticket.status,
        due_at=ticket.due_at,
        overdue=ticket.due_at is not None
        and ticket.due_at < now
        and ticket.status not in CLOSED_STATUSES,
    )
