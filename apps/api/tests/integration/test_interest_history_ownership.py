"""An owned audit row never grants access to a foreign interest through its relationship."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.interests.models import InterestNotification, UserInterest
from src.domains.interests.notifications_router import get_interest_notification_history
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("link", ["foreign", "owned", "deleted", "fresh"])
async def test_history_preserves_owned_messages_without_a_foreign_topic(
    async_session: AsyncSession, test_user: User, test_superuser: User, link: str
) -> None:
    owner, foreign = test_user.id, test_superuser.id
    interest = UserInterest(
        user_id=owner if link in {"owned", "fresh"} else foreign,
        topic="Own topic" if link in {"owned", "fresh"} else "FOREIGN_PRIVATE_TOPIC",
        category="science",
        last_mentioned_at=datetime.now(UTC),
    )
    async_session.add(interest)
    await async_session.flush()
    notification = InterestNotification(
        user_id=owner,
        interest=None if link == "deleted" else interest,
        run_id=str(uuid4()),
        content_hash="a" * 64,
        content="Message sent to owner",
        source="llm",
    )
    async_session.add_all(
        [
            notification,
            InterestNotification(
                user_id=foreign,
                interest=interest,
                run_id=str(uuid4()),
                content_hash="b" * 64,
                content="Foreign notification",
                source="llm",
            ),
        ]
    )
    await async_session.commit()
    if link == "fresh":
        await async_session.execute(
            update(InterestNotification)
            .where(InterestNotification.id == notification.id)
            .values(content="Fresh owner content")
            .execution_options(synchronize_session=False)
        )
        await async_session.commit()
    result = await get_interest_notification_history(
        limit=20, offset=0, user=test_user, db=async_session
    )
    assert result.total == 1 and len(result.notifications) == 1
    assert result.notifications[0].content == (
        "Fresh owner content" if link == "fresh" else "Message sent to owner"
    )
    assert result.notifications[0].topic == ("Own topic" if link in {"owned", "fresh"} else None)
    assert "FOREIGN_PRIVATE_TOPIC" not in result.model_dump_json()
