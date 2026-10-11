"""The UI export covers every owned status beyond the display limit."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from src.core.constants import INTEREST_USER_LIST_LIMIT
from src.domains.interests.models import UserInterest
from src.domains.interests.router import export_interests
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_export_is_complete_owned_and_contains_only_the_public_source_fields(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    other = User(
        id=uuid4(),
        email=f"export-other-{uuid4()}@example.test",
        full_name="Other",
        is_active=True,
        is_verified=True,
    )
    async_session.add(other)
    await async_session.flush()
    count = INTEREST_USER_LIST_LIMIT + 3
    async_session.add_all(
        [
            UserInterest(
                user_id=test_user.id,
                topic=f"Export topic {index}",
                category="science",
                status=("active", "blocked", "dormant")[index % 3],
                last_mentioned_at=datetime.now(UTC),
                embedding=[0.1, 0.2],
            )
            for index in range(count)
        ]
    )
    async_session.add(
        UserInterest(
            user_id=other.id,
            topic="Foreign secret",
            category="science",
            last_mentioned_at=datetime.now(UTC),
        )
    )
    await async_session.commit()
    response = await export_interests(export_format="json", user=test_user, db=async_session)
    assert isinstance(response, StreamingResponse)
    chunks = [chunk async for chunk in response.body_iterator]
    result = json.loads(b"".join(chunks))
    await response._reader.close()
    assert result["total_interests"] == count
    assert len(result["interests"]) == count
    assert {item["status"] for item in result["interests"]} == {"active", "blocked", "dormant"}
    assert all(
        set(item)
        == {
            "id",
            "topic",
            "category",
            "status",
            "positive_signals",
            "negative_signals",
            "weight",
            "last_mentioned_at",
            "last_notified_at",
            "created_at",
        }
        for item in result["interests"]
    )
    assert "Foreign secret" not in str(result)
