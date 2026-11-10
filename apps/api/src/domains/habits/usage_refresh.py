"""One night of usage learning for one person (ADR-375).

The order is the contract: read the ledger once, gather every observation,
bring the recurring-need rows in line, judge the proposals, bring the
proposal rows in line, count what moved. It runs inside the nightly
recompute (and the person's « Recalculer »), on the recompute's session,
before any activity skip — a quiet person's proposals still reopen, lapse
and withdraw.
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.time_utils import resolve_user_timezone
from src.domains.habits.proposal_repository import HabitProposalRepository
from src.domains.habits.proposal_rules import ProposalThresholds, evaluate_proposals
from src.domains.habits.proposal_sync import ProposalSyncOutcome, sync_proposals
from src.domains.habits.recurrence_sync import RecurringSyncOutcome, sync_recurring_habits
from src.domains.habits.repository import HabitsRepository
from src.domains.habits.usage_observations import gather_usage_observations, read_ledger


@dataclass(frozen=True, slots=True)
class UsageRefreshOutcome:
    """What one night of usage learning did."""

    recurring: RecurringSyncOutcome
    proposals: ProposalSyncOutcome


async def refresh_usage(
    db: AsyncSession, user: Any, *, settings: Any, now: datetime
) -> UsageRefreshOutcome:
    """Learn tonight's needs and bring the person's proposals in line.

    Args:
        db: The recompute's session; the caller commits.
        user: The ``User`` row.
        settings: The application settings.
        now: The instant of the run (UTC).

    Returns:
        The two sync outcomes (also counted on the habits metrics).
    """
    tz = resolve_user_timezone(user)
    ledger = await read_ledger(user.id)
    observations = await gather_usage_observations(
        db, user, ledger=ledger, today=now.astimezone(tz).date(), settings=settings
    )
    recurring = await sync_recurring_habits(
        HabitsRepository(db), user.id, observations.needs, ledger, tz=tz, settings=settings
    )
    proposals = await sync_proposals(
        HabitProposalRepository(db),
        user.id,
        evaluate_proposals(observations, ProposalThresholds.from_settings(settings)),
        now=now,
    )
    _count(recurring, proposals)
    return UsageRefreshOutcome(recurring=recurring, proposals=proposals)


def _count(recurring: RecurringSyncOutcome, proposals: ProposalSyncOutcome) -> None:
    """Count what moved — best-effort, a metric never breaks the recompute."""
    with suppress(Exception):
        from src.infrastructure.observability.metrics_habits import (
            habit_proposals_total,
            recurring_habits_synced_total,
        )

        if recurring.skipped:
            recurring_habits_synced_total.labels(action="skipped").inc()
        for action in ("created", "updated", "demoted", "blocked", "capped"):
            count = getattr(recurring, action)
            if count:
                recurring_habits_synced_total.labels(action=action).inc(count)
        for (kind, transition), count in proposals.transitions.items():
            habit_proposals_total.labels(kind=kind, transition=transition).inc(count)
