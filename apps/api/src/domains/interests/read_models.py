"""UI and explicit management tools share complete source projections and weight policy."""

from datetime import datetime

from src.core.config import settings
from src.domains.interests.models import InterestCategory, InterestStatus, UserInterest
from src.domains.interests.repository import InterestRepository
from src.domains.interests.schemas import InterestResponse, InterestSettingsResponse
from src.domains.users.models import User


def user_to_settings_response(user: User) -> InterestSettingsResponse:
    return InterestSettingsResponse.model_validate(user, from_attributes=True)


def interest_to_response(
    interest: UserInterest, repo: InterestRepository, *, now: datetime | None = None
) -> InterestResponse:
    return InterestResponse(
        id=interest.id,
        topic=interest.topic,
        category=InterestCategory(interest.category),
        weight=repo.calculate_effective_weight(
            interest, decay_rate_per_day=settings.interest_decay_rate_per_day, now=now
        ),
        status=InterestStatus(interest.status),
        positive_signals=interest.positive_signals,
        negative_signals=interest.negative_signals,
        last_mentioned_at=interest.last_mentioned_at,
        last_notified_at=interest.last_notified_at,
        created_at=interest.created_at,
        subject=interest.subject,
    )
