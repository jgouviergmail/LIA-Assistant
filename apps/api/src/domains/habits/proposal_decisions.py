"""The person's decision on a habit proposal — one transaction, claim then act (ADR-375).

Three verdicts: ``accept`` (the proposal is carried out and may reopen after
``HABITS_PROPOSAL_RESURFACE_DAYS`` if it holds again), ``dismiss`` (« later »,
reopens after ``HABITS_PROPOSAL_SNOOZE_DAYS``) and ``refuse`` (« never », a
tombstone; three of one kind silence the kind).

The order is the contract (ADR-263: an effect is claimed before it happens):

1. the person's row is locked — the order every act below takes too, so two
   clicks, or a click and the nightly sync, never deadlock;
2. the proposal is CLAIMED by one conditional statement on its OPEN status —
   the click that loses a race reads « not open », never a second act;
3. on ``accept``, the kind's handler acts inside the same transaction; when it
   refuses (the routine cap, a routine gone or changed, settings changed), the
   whole transaction rolls back: no act, no claim, the proposal stays open and
   the refusal names a stable reason the card translates;
4. one commit.

A decision on a need's proposal is also a signal on the need itself
(``positive_signals`` / ``negative_signals``, shown in the habits panel).
Nothing is written to the decision registers: a click a person makes, with no
model involved, is not an act of the assistant (owner decision 2026-10-30).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, NoReturn
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, raise_not_found_or_unauthorized
from src.domains.habits import proposal_handlers  # noqa: F401 — installs habits' own handlers
from src.domains.habits.models import HabitKind, HabitProposal, ProposalKind, ProposalStatus
from src.domains.habits.proposal_actions import (
    ProposalActionRefused,
    ProposalActionResult,
    proposal_action,
)
from src.domains.habits.proposal_repository import HabitProposalRepository
from src.domains.habits.repository import HabitsRepository
from src.domains.users.models import User
from src.infrastructure.observability.metrics_habits import (
    habit_proposal_action_failures_total,
    habit_proposals_total,
)

logger = structlog.get_logger(__name__)

#: The stable codes a refused decision carries (``detail.error_code``).
PROPOSAL_NOT_OPEN = "PROPOSAL_NOT_OPEN"
PROPOSAL_ACTION_REFUSED = "PROPOSAL_ACTION_REFUSED"


class ProposalVerdict(StrEnum):
    """What the person answered."""

    ACCEPT = "accept"
    DISMISS = "dismiss"
    REFUSE = "refuse"


_STATUS_OF: dict[ProposalVerdict, ProposalStatus] = {
    ProposalVerdict.ACCEPT: ProposalStatus.ACCEPTED,
    ProposalVerdict.DISMISS: ProposalStatus.DISMISSED,
    ProposalVerdict.REFUSE: ProposalStatus.REFUSED,
}


@dataclass(frozen=True, slots=True)
class ProposalDecision:
    """A recorded decision.

    Attributes:
        proposal: The decided row.
        routine_id: The routine an accepted proposal created, moved or opens.
    """

    proposal: HabitProposal
    routine_id: UUID | None = None


def _resurface_after(verdict: ProposalVerdict, settings: Any, now: datetime) -> datetime | None:
    if verdict is ProposalVerdict.ACCEPT:
        return now + timedelta(days=int(settings.habits_proposal_resurface_days))
    if verdict is ProposalVerdict.DISMISS:
        return now + timedelta(days=int(settings.habits_proposal_snooze_days))
    return None


def _not_open() -> NoReturn:
    raise ResourceConflictError("habit_proposal", detail={"error_code": PROPOSAL_NOT_OPEN})


async def _carry_out(
    db: AsyncSession, user: User, proposal: HabitProposal, kind: ProposalKind
) -> ProposalActionResult:
    """Run the kind's handler; on a refusal, roll EVERYTHING back and say why."""
    user_id = user.id
    try:
        return await proposal_action(kind)(db, user, proposal)
    except ProposalActionRefused as refusal:
        await db.rollback()
        _count_failure(kind, refusal.reason.value)
        logger.info(
            "habit_proposal_action_refused",
            user_id=str(user_id),
            kind=kind.value,
            reason=refusal.reason.value,
        )
        raise ResourceConflictError(
            "habit_proposal",
            detail={"error_code": PROPOSAL_ACTION_REFUSED, "reason": refusal.reason.value},
        ) from None


async def decide_proposal(
    db: AsyncSession,
    user: User,
    proposal_id: UUID,
    verdict: ProposalVerdict,
    *,
    settings: Any,
    now: datetime,
) -> ProposalDecision:
    """Record the person's decision and, on ``accept``, carry the proposal out.

    Args:
        db: The request's session; this function commits, or rolls back on a
            refusal.
        user: The person deciding.
        proposal_id: The proposal.
        verdict: Their answer.
        settings: The application settings (snooze and resurface delays).
        now: The decision instant (UTC).

    Returns:
        The decision.

    Raises:
        ResourceNotFoundError: When the proposal is not theirs, or does not exist.
        ResourceConflictError: ``PROPOSAL_NOT_OPEN`` when it was already decided
            or withdrawn; ``PROPOSAL_ACTION_REFUSED`` with a ``reason`` when the
            act no longer matches what the person was shown.
    """
    user_id = user.id
    repo = HabitProposalRepository(db)
    await repo.lock_owner(user_id)
    proposal = await repo.get_owned(proposal_id, user_id)
    if proposal is None:
        raise_not_found_or_unauthorized("habit_proposal", proposal_id)
    kind = ProposalKind(proposal.kind)
    status = _STATUS_OF[verdict]
    decided = await repo.decide(
        proposal_id, user_id, status, _resurface_after(verdict, settings, now), now=now
    )
    if decided is None:
        await db.rollback()
        _not_open()
    if kind is ProposalKind.AUTOMATE_NEED and verdict is not ProposalVerdict.DISMISS:
        await HabitsRepository(db).record_feedback(
            user_id,
            HabitKind.RECURRING_REQUEST.value,
            decided.key,
            positive=verdict is ProposalVerdict.ACCEPT,
        )
    result = (
        await _carry_out(db, user, decided, kind)
        if verdict is ProposalVerdict.ACCEPT
        else ProposalActionResult()
    )
    await db.commit()
    _count_decision(kind, status)
    logger.info(
        "habit_proposal_decided",
        user_id=str(user_id),
        kind=kind.value,
        status=status.value,
        routine_id=str(result.routine_id) if result.routine_id else None,
    )
    return ProposalDecision(proposal=decided, routine_id=result.routine_id)


def _count_decision(kind: ProposalKind, status: ProposalStatus) -> None:
    habit_proposals_total.labels(kind=kind.value, transition=status.value).inc()


def _count_failure(kind: ProposalKind, reason: str) -> None:
    habit_proposal_action_failures_total.labels(kind=kind.value, reason=reason).inc()
