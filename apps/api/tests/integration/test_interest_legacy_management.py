"""Read facts need not satisfy today's sparse write constraints to be editable or removable."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.interest_removal import prepare_interest_removal
from src.domains.agents.application.interest_removal_schemas import InterestDeleteRequest
from src.domains.interests.models import UserInterest
from src.domains.interests.router import update_interest
from src.domains.interests.schemas import InterestUpdate
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("operation", ["rename", "signals", "delete_proposal"])
async def test_legacy_short_topic_can_be_managed_without_validating_unchanged_fields_as_writes(
    async_session: AsyncSession, test_user: User, operation: str
) -> None:
    row = UserInterest(
        user_id=test_user.id,
        topic="X",
        category="science",
        positive_signals=3,
        negative_signals=1,
        last_mentioned_at=datetime.now(UTC),
    )
    async_session.add(row)
    await async_session.commit()
    identity = row.id
    with patch(
        "src.domains.interests.router.generate_interest_embedding",
        new_callable=AsyncMock,
        return_value=None,
    ):
        if operation == "delete_proposal":
            draft = await prepare_interest_removal(
                async_session, test_user.id, InterestDeleteRequest(interest_id=identity)
            )
            assert draft.before["interest_to_delete"]["configuration"]["topic"] == "X"
        else:
            data = (
                InterestUpdate(topic="Renamed topic")
                if operation == "rename"
                else InterestUpdate(negative_signals=0)
            )
            result = await update_interest(identity, data, test_user, async_session)
            assert result.topic == ("Renamed topic" if operation == "rename" else "X")
