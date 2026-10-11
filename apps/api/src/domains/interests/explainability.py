"""Owned fresh interest facts and one source weight explanation shared by UI and tools."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from src.core.config import settings
from src.core.constants import INTEREST_DECAY_FLOOR
from src.core.exceptions import raise_interest_not_found
from src.domains.interests.models import UserInterest
from src.domains.interests.repository import InterestRepository
from src.domains.interests.schemas import InterestExplanation


async def get_owned_interest(db: AsyncSession, actor_id: UUID, interest_id: UUID) -> UserInterest:
    row = await db.scalar(
        select(UserInterest)
        .where(UserInterest.user_id == actor_id, UserInterest.id == interest_id)
        .options(defer(UserInterest.embedding))
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise_interest_not_found(interest_id)
    assert row is not None
    return row


def explain_interest(
    row: UserInterest, repo: InterestRepository, *, now: datetime | None = None
) -> InterestExplanation:
    observed_at = now or datetime.now(UTC)
    return InterestExplanation(
        positive_signals=row.positive_signals,
        negative_signals=row.negative_signals,
        prior_alpha=settings.interest_prior_alpha,
        prior_beta=settings.interest_prior_beta,
        base_weight=repo.calculate_weight(row),
        decay_rate_per_day=settings.interest_decay_rate_per_day,
        decay_floor=INTEREST_DECAY_FLOOR,
        days_since_last_mention=max(0, (observed_at - row.last_mentioned_at).days),
        effective_weight=repo.calculate_effective_weight(row, now=observed_at),
        last_mentioned_at=row.last_mentioned_at,
        last_notified_at=row.last_notified_at,
        status=row.status,
        dormant_since=row.dormant_since,
    )
