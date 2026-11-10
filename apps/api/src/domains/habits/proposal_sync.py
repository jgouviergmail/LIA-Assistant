"""The nightly life of a proposal (ADR-375).

The rules say what SHOULD be open tonight; this module brings the person's
``habit_proposals`` rows in line, through the repository's conditional
statements only (never a read-modify-write a click could race):

- a new candidate opens its row; an open row follows its facts;
- a dismissed or accepted row reopens once ``resurface_after`` has passed and
  the rule holds again; a refusal is never touched;
- an open row whose rule stopped holding is withdrawn — unless its kind was
  HELD tonight (an observation missing): doubt never withdraws.

Every move is counted by kind and transition, so a silent rule shows on a
dashboard rather than in a person's empty inbox.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domains.habits.models import HabitProposal, ProposalKind, ProposalStatus
from src.domains.habits.proposal_repository import HabitProposalRepository
from src.domains.habits.proposal_rules import ProposalCandidate, ProposalEvaluation

_DECIDED = (ProposalStatus.DISMISSED.value, ProposalStatus.ACCEPTED.value)


@dataclass(frozen=True, slots=True)
class ProposalSyncOutcome:
    """What one sync did, by ``(kind, transition)``.

    Transitions: ``opened``, ``refreshed``, ``reopened``, ``withdrawn``,
    ``held`` (an open proposal kept because its kind could not be judged).
    """

    transitions: dict[tuple[str, str], int]


async def _follow(
    repo: HabitProposalRepository,
    user_id: UUID,
    candidate: ProposalCandidate,
    row: HabitProposal | None,
    now: datetime,
) -> str | None:
    """The transition a candidate held tonight makes, or None when nothing moved."""
    kind = candidate.kind.value
    if row is None:
        opened = await repo.open(user_id, kind, candidate.key, candidate.payload)
        return "opened" if opened else None
    if row.status == ProposalStatus.OPEN.value:
        if row.payload == candidate.payload:
            return None
        return "refreshed" if await repo.refresh_open(row.id, candidate.payload) else None
    if row.status in _DECIDED and await repo.reopen(row.id, candidate.payload, now=now):
        return "reopened"
    return None


async def _let_go(
    repo: HabitProposalRepository, row: HabitProposal, held: frozenset[ProposalKind]
) -> str | None:
    """The transition an open row no rule holds tonight makes — doubt never withdraws."""
    if row.kind in held:
        return "held"
    return "withdrawn" if await repo.withdraw_open(row.id) else None


async def sync_proposals(
    repo: HabitProposalRepository,
    user_id: UUID,
    evaluation: ProposalEvaluation,
    *,
    now: datetime,
) -> ProposalSyncOutcome:
    """Bring the person's proposals in line with tonight's evaluation.

    Args:
        repo: The proposals repository bound to the recompute's session; the
            caller commits.
        user_id: Owner.
        evaluation: The candidates and the held kinds.
        now: The instant reopen dates are compared with.

    Returns:
        The counted transitions.
    """
    counts: Counter[tuple[str, str]] = Counter()
    rows = {(row.kind, row.key): row for row in await repo.list_for_user(user_id)}
    wanted = {(c.kind.value, c.key): c for c in evaluation.candidates}
    for identity, candidate in wanted.items():
        transition = await _follow(repo, user_id, candidate, rows.get(identity), now)
        if transition:
            counts[(identity[0], transition)] += 1
    for identity, row in rows.items():
        if row.status != ProposalStatus.OPEN.value or identity in wanted:
            continue
        transition = await _let_go(repo, row, evaluation.held)
        if transition:
            counts[(identity[0], transition)] += 1
    return ProposalSyncOutcome(transitions=dict(counts))
