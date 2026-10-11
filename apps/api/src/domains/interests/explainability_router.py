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

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.interests.explainability import explain_interest, get_owned_interest
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
    interest = await get_owned_interest(db, user.id, interest_id)
    return explain_interest(interest, repo, now=datetime.now(UTC))


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
    await get_owned_interest(db, user.id, interest_id)

    references = await ProvenanceRepository(db).resolve_for(
        user_id=user.id, interest_id=interest_id
    )
    return ProvenanceResponse.from_references(references)
