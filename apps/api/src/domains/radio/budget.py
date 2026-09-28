"""What a listener's radio may spend over a rolling day (ADR-324 decision 37).

The radio bills a listener's own runs — a session (``radio_<hex>``) and each
article translation (``radio_article_<hex>``) — and the owner bounds their sum
over any 24 hours (``RADIO_BUDGET_24H_EUR``, 0 = no bound) so that nobody can
leave a station playing at the platform's expense. The bound is the radio's
own, on top of the account's ceilings (``spend_blocked``), never instead of
them.

What a run spent is its ledger row, every family (``billed_cost_sql``, ADR-272):
one figure, the one the bar and the closing card show. A run counts WHOLE
while its last spend lies inside the window — a session is filed once per
production, so ``updated_at`` is its last euro. When that errs, it costs the
listener a little waiting, never the platform a euro past the bound: a session
partly spent before the window still counts in full, so no 24 hours ever hold
more than the bound, plus
what was already under way when it was crossed (it is asked before each
production, flash and translation).

Three doors ask, each at its own moment: a start (refused, with the instant it
lifts), the loop before every production (the session ends as ``budget``), and
an article's translation (the original is shown, said so). The settings read
the same figure (``GET /radio/budget``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy import select

from src.core.config import settings
from src.domains.chat.models import MessageTokenSummary
from src.domains.radio.constants import BUDGET_WINDOW_SECONDS, RADIO_RUN_ID_PREFIX
from src.domains.usage_limits.enforcement import spend_blocked
from src.infrastructure.database.session import get_db_context

_WINDOW = timedelta(seconds=BUDGET_WINDOW_SECONDS)


@dataclass(frozen=True, slots=True)
class RadioSpend:
    """One radio run of the listener's, as the budget counts it.

    Attributes:
        at: Its last spend (the run's row was last written then).
        eur: Everything it cost, every family.
    """

    at: datetime
    eur: float


@dataclass(frozen=True, slots=True)
class BudgetStatus:
    """The listener's radio over the rolling day.

    Attributes:
        limit_eur: The bound (0 = none).
        spent_eur: What their radio spent over the window.
        lifts_at: When enough of it leaves the window to play again — set only
            while the bound is reached.
    """

    limit_eur: float
    spent_eur: float
    lifts_at: datetime | None

    @property
    def reached(self) -> bool:
        """Whether the radio may spend nothing more for now."""
        return self.limit_eur > 0 and self.spent_eur >= self.limit_eur


class BudgetReader(Protocol):
    """Reads a listener's radio budget — :func:`listener_budget`, bound where it is asked."""

    async def __call__(self, user_id: UUID, *, now: datetime) -> BudgetStatus:
        """The bound, what the window holds, and when a reached bound lifts."""
        ...


def budget_status(spends: Sequence[RadioSpend], *, limit_eur: float, now: datetime) -> BudgetStatus:
    """The listener's radio budget at ``now`` — pure.

    Args:
        spends: Their radio runs (those older than the window are ignored).
        limit_eur: The bound (0 = none).
        now: The instant (timezone-aware).

    Returns:
        What the window holds and, at the bound, the first instant at which the
        runs that have left it bring it back under: the oldest leave first.
    """
    inside = sorted((spend for spend in spends if spend.at > now - _WINDOW), key=lambda s: s.at)
    spent = sum(spend.eur for spend in inside)
    status = BudgetStatus(limit_eur=limit_eur, spent_eur=spent, lifts_at=None)
    if not status.reached:
        return status
    remaining = spent
    for spend in inside[:-1]:
        remaining -= spend.eur
        if remaining < limit_eur:
            return BudgetStatus(limit_eur, spent, spend.at + _WINDOW)
    # A reached bound is positive, so the window holds a run; once the last has
    # left it, an empty window is under any bound.
    return BudgetStatus(limit_eur, spent, inside[-1].at + _WINDOW)


async def radio_spends(user_id: UUID, *, since: datetime) -> list[RadioSpend]:
    """The listener's radio runs whose last spend is after ``since``.

    Args:
        user_id: The listener.
        since: The window's start.

    Returns:
        Each run's last spend and total, in no particular order.
    """
    statement = select(MessageTokenSummary.updated_at, MessageTokenSummary.billed_cost_sql()).where(
        MessageTokenSummary.user_id == user_id,
        # ``autoescape``: the prefix's underscore is a character, never LIKE's wildcard.
        MessageTokenSummary.run_id.startswith(RADIO_RUN_ID_PREFIX, autoescape=True),
        MessageTokenSummary.updated_at > since,
    )
    async with get_db_context() as db:
        rows = (await db.execute(statement)).all()
    return [RadioSpend(at=at, eur=float(eur or 0)) for at, eur in rows]


async def listener_budget(user_id: UUID, *, now: datetime) -> BudgetStatus:
    """The listener's radio budget now — nothing read when the instance sets no bound.

    Args:
        user_id: The listener.
        now: The instant (timezone-aware).

    Returns:
        The bound, what the window holds, and when a reached bound lifts.
    """
    limit = settings.radio_budget_24h_eur
    if limit <= 0:
        return BudgetStatus(limit_eur=0.0, spent_eur=0.0, lifts_at=None)
    return budget_status(await radio_spends(user_id, since=now - _WINDOW), limit_eur=limit, now=now)


async def radio_spend_blocked(user_id: UUID, *, now: datetime) -> bool:
    """Whether the next production may not be paid: an account ceiling, or the radio's own.

    Args:
        user_id: The listener.
        now: The instant (timezone-aware).

    Returns:
        True when the session must stop producing.
    """
    if await spend_blocked(user_id):
        return True
    return (await listener_budget(user_id, now=now)).reached


__all__ = [
    "BudgetReader",
    "BudgetStatus",
    "RadioSpend",
    "budget_status",
    "listener_budget",
    "radio_spend_blocked",
    "radio_spends",
]
