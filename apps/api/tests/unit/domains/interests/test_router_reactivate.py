"""Unit tests for the reactivate route guards (ownership + status)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.interests.models import InterestStatus, UserInterest
from src.domains.interests.router import reactivate_interest


def _interest(status: str, owner_id: uuid.UUID) -> UserInterest:
    interest = UserInterest(
        user_id=owner_id,
        topic="ml",
        category="technology",
        positive_signals=1,
        negative_signals=0,
        status=status,
        last_mentioned_at=datetime.now(UTC),
    )
    interest.id = uuid.uuid4()
    return interest


@pytest.mark.unit
async def test_reactivate_rejects_non_dormant_with_conflict() -> None:
    user = MagicMock()
    user.id = uuid.uuid4()
    db = AsyncMock()
    interest = _interest(InterestStatus.ACTIVE.value, user.id)

    with patch("src.domains.interests.router.InterestRepository") as mock_repo_cls:
        repo = mock_repo_cls.return_value
        repo.get_by_id = AsyncMock(return_value=interest)
        with pytest.raises(ResourceConflictError):
            await reactivate_interest(interest_id=interest.id, user=user, db=db)


@pytest.mark.unit
async def test_reactivate_rejects_foreign_interest_with_not_found() -> None:
    user = MagicMock()
    user.id = uuid.uuid4()
    db = AsyncMock()
    interest = _interest(InterestStatus.DORMANT.value, owner_id=uuid.uuid4())

    with patch("src.domains.interests.router.InterestRepository") as mock_repo_cls:
        repo = mock_repo_cls.return_value
        repo.get_by_id = AsyncMock(return_value=interest)
        with pytest.raises(ResourceNotFoundError):
            await reactivate_interest(interest_id=interest.id, user=user, db=db)
