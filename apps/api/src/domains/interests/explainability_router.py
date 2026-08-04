"""Why LIA thinks an interest matters — the coefficients, and the signal.

Its own module rather than more endpoints in ``router.py``: that file sits at
its frozen size ceiling and the doctrine is to extract, never to bump the cap.
The concern is distinct too — "which interests exist and how they are tuned"
is what the main router is about; this answers "why does this one weigh what it
weighs, and where did it come from?".

**The weight is EXPLAINED, never gamified.** What is published is the formula's
inputs and the formula's coefficients, so the reader can reconstruct the number
LIA actually applies:

    (alpha0 + positives) / (alpha0 + positives + beta0 + negatives)
        * max(floor, 1 - decay_rate * days_since_last_mention)

No rank, no level, no comparison with anyone. A Beta mean IS an uncertainty
estimate, and saying "two signals, so this is a guess" is more useful to
someone deciding whether to block a subject than any score could be.

Every coefficient comes from settings and is published beside the value it
produces — an enforced constant the reader cannot see is a trap (ADR-184), and
this one used to differ between what the API displayed and what the ranking
applied (fixed the same day, `get_top_weighted_interests`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    INTEREST_DECAY_FLOOR,
)
from src.core.dependencies import get_db
from src.core.exceptions import raise_interest_not_found
from src.core.session_dependencies import get_current_active_session
from src.domains.interests.repository import InterestRepository
from src.domains.interests.schemas import InterestExplanation
from src.domains.shared.provenance_repository import ProvenanceRepository
from src.domains.shared.schemas import ProvenanceResponse
from src.domains.users.models import User

router = APIRouter(prefix="/interests", tags=["Interests"])


@router.get(
    "/{interest_id}/explanation",
    response_model=InterestExplanation,
    summary="Why this interest weighs what it weighs",
    description=(
        "The inputs AND the coefficients of the weight, so the number can be "
        "reconstructed rather than trusted. No rank, no level, no comparison: "
        "explaining the uncertainty is more useful than a score."
    ),
)
async def get_interest_explanation(
    interest_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> InterestExplanation:
    """Everything the weight is made of, for one interest.

    Args:
        interest_id: The interest being questioned.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        The signals, the dates, and the published coefficients.

    Raises:
        ResourceNotFoundError: Unknown interest, or one belonging to another
            account — the two answer identically.
    """
    repo = InterestRepository(db)
    interest = await repo.get_by_id(interest_id)
    if not interest or interest.user_id != user.id:
        raise_interest_not_found(interest_id)

    now = datetime.now(UTC)
    days_since = max(0, (now - interest.last_mentioned_at).days)
    decay_rate = settings.interest_decay_rate_per_day

    return InterestExplanation(
        positive_signals=interest.positive_signals,
        negative_signals=interest.negative_signals,
        prior_alpha=settings.interest_prior_alpha,
        prior_beta=settings.interest_prior_beta,
        base_weight=repo.calculate_weight(interest),
        decay_rate_per_day=decay_rate,
        decay_floor=INTEREST_DECAY_FLOOR,
        days_since_last_mention=days_since,
        # The SAME call the ranking makes, with the same default — the two
        # disagreed until 2026-08-04, and an explanation of a number nobody
        # applies is worse than no explanation.
        effective_weight=repo.calculate_effective_weight(interest, now=now),
        last_mentioned_at=interest.last_mentioned_at,
        last_notified_at=interest.last_notified_at,
        status=interest.status,
        dormant_since=interest.dormant_since,
    )


@router.get(
    "/{interest_id}/provenance",
    response_model=ProvenanceResponse,
    summary="The signal this interest came from",
    description=(
        "Bounded references, resolved LIVE. A reference whose conversation the "
        "reader has since deleted comes back as a tombstone: dated, sourceless "
        "and textless."
    ),
)
async def get_interest_provenance(
    interest_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ProvenanceResponse:
    """The conversations behind one interest.

    Args:
        interest_id: The interest being questioned.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        The references, newest first, and the cap the trail is kept at.

    Raises:
        ResourceNotFoundError: Unknown interest, or one belonging to another
            account.
    """
    interest = await InterestRepository(db).get_by_id(interest_id)
    if not interest or interest.user_id != user.id:
        raise_interest_not_found(interest_id)

    references = await ProvenanceRepository(db).resolve_for(
        user_id=user.id, interest_id=interest_id
    )
    return ProvenanceResponse.from_references(references)
