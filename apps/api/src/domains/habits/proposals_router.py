"""Habit proposals router — the open proposals and the person's decisions (ADR-375).

Mounted under the habits deployment flag, beside the habits control surface.
Reading answers an EMPTY page with ``learning_enabled=false`` when habit
learning is off for the person or the instance — never « nothing to propose »
for « nothing served ». Deciding ACTS (a routine created or moved, the
notification preferences changed), so the operator's switch guards it at the
route and the person's own switch is read with it (``proposals_served``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import HABITS_PROPOSALS_PAGE_MAX
from src.core.dependencies import get_db
from src.core.exceptions import AuthorizationError
from src.core.session_dependencies import get_current_active_session
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.habits.capability import proposals_served
from src.domains.habits.models import ProposalKind, ProposalStatus
from src.domains.habits.proposal_decisions import ProposalVerdict, decide_proposal
from src.domains.habits.proposal_repository import HabitProposalRepository
from src.domains.habits.proposal_schemas import (
    HabitProposalDecisionResponse,
    HabitProposalResponse,
    HabitProposalsPage,
)
from src.domains.users.models import User

router = APIRouter(prefix="/habits/proposals", tags=["Habits"])


@router.get(
    "",
    response_model=HabitProposalsPage,
    summary="Open habit proposals",
    description="What LIA proposes from what it learned, newest first, with the exact total.",
)
async def list_habit_proposals(
    limit: int = Query(default=20, ge=1, le=HABITS_PROPOSALS_PAGE_MAX),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> HabitProposalsPage:
    """One page of the person's open proposals."""
    if not await proposals_served(current_user):
        return HabitProposalsPage(proposals=[], total=0, learning_enabled=False)
    rows, total = await HabitProposalRepository(db).page_open(
        current_user.id, limit=limit, offset=offset
    )
    return HabitProposalsPage(
        proposals=[HabitProposalResponse.from_row(row) for row in rows],
        total=total,
        learning_enabled=True,
    )


@router.post(
    "/{proposal_id}/{verdict}",
    dependencies=capability_dependencies(PlatformCapability.HABITS),
    response_model=HabitProposalDecisionResponse,
    summary="Accept, put off or refuse a habit proposal",
    description=(
        "accept carries the proposal out (a routine created or moved, the notification "
        "preferences changed); dismiss puts it off; refuse never shows it again. A "
        "refused act answers 409 with a stable reason and leaves the proposal open."
    ),
)
async def decide_habit_proposal(
    proposal_id: UUID,
    verdict: ProposalVerdict,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> HabitProposalDecisionResponse:
    """Record the person's decision."""
    if not await proposals_served(current_user):
        raise AuthorizationError(detail={"error_code": "FEATURE_DISABLED"})
    decision = await decide_proposal(
        db, current_user, proposal_id, verdict, settings=settings, now=datetime.now(UTC)
    )
    return HabitProposalDecisionResponse(
        id=decision.proposal.id,
        kind=ProposalKind(decision.proposal.kind),
        status=ProposalStatus(decision.proposal.status),
        routine_id=decision.routine_id,
    )
