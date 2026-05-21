"""Unit tests for InterestRepository.reactivate (reset-to-fresh)."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.domains.interests.models import InterestStatus, UserInterest
from src.domains.interests.repository import InterestRepository


def _dormant_interest() -> UserInterest:
    interest = UserInterest(
        user_id=uuid.uuid4(),
        topic="machine learning",
        category="technology",
        positive_signals=7,
        negative_signals=4,
        status=InterestStatus.DORMANT.value,
        last_mentioned_at=datetime.now(UTC) - timedelta(days=60),
    )
    interest.id = uuid.uuid4()
    interest.dormant_since = datetime.now(UTC) - timedelta(days=30)
    interest.last_notified_at = datetime.now(UTC) - timedelta(days=40)
    return interest


@pytest.mark.unit
async def test_reactivate_resets_to_fresh_state() -> None:
    db = AsyncMock()
    repo = InterestRepository(db)
    interest = _dormant_interest()

    await repo.reactivate(interest)

    assert interest.status == InterestStatus.ACTIVE.value
    assert interest.positive_signals == 1
    assert interest.negative_signals == 0
    assert interest.dormant_since is None
    assert interest.last_notified_at is None
    assert (datetime.now(UTC) - interest.last_mentioned_at).total_seconds() < 5
    db.flush.assert_awaited_once()
