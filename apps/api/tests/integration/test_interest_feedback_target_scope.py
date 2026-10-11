"""A notification verdict must belong to the selected interest as well as its owner."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.interests.models import InterestNotification, UserInterest
from src.domains.interests.repository import InterestNotificationRepository
from src.domains.interests.router import submit_feedback
from src.domains.interests.schemas import InterestFeedbackRequest
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_run_id_cannot_attribute_feedback_to_another_owned_interest(
    async_session: AsyncSession, test_user: User
) -> None:
    owner = test_user.id
    selected, other = uuid4(), uuid4()
    async_session.add_all(
        [
            UserInterest(
                id=identity,
                user_id=owner,
                topic=f"Topic {identity}",
                category="science",
                last_mentioned_at=datetime.now(UTC),
            )
            for identity in (selected, other)
        ]
    )
    await async_session.flush()
    row = InterestNotification(
        user_id=owner,
        interest_id=other,
        run_id=f"interest-{uuid4()}",
        content="Delivered content",
        content_hash="a" * 64,
        source="test",
    )
    async_session.add(row)
    await async_session.commit()
    repository = InterestNotificationRepository(async_session)
    with patch("src.domains.habits.presence.record_presence", new_callable=AsyncMock):
        await submit_feedback(
            selected,
            InterestFeedbackRequest(feedback="thumbs_up", run_id=row.run_id),
            test_user,
            async_session,
        )
    await async_session.refresh(row)
    assert row.user_feedback is None and row.feedback_at is None
    changed = await repository.update_feedback_by_run_id(
        run_id=row.run_id, user_id=owner, interest_id=other, feedback="thumbs_up"
    )
    await async_session.commit()
    await async_session.refresh(row)
    assert changed and row.user_feedback == "thumbs_up" and row.feedback_at is not None
