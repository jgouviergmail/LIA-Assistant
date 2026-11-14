"""An annex answer cannot acknowledge a proactive opening in Main."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.domains.conversations.models import ConversationMessage
from src.domains.proactive_discussions.models import DiscussionOpeningRecord
from src.domains.proactive_discussions.replies import has_reply
from tests.fixtures.learning_sources import Sources
from tests.fixtures.learning_sources import sources as sources

pytestmark = pytest.mark.integration


async def test_only_a_visible_timely_main_reply_answers_its_opening(
    async_engine: AsyncEngine, sources: Sources
) -> None:
    now = datetime.now(UTC)
    opening = DiscussionOpeningRecord(
        user_id=sources.main.owner_id,
        conversation_id=sources.main.id,
        created_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(minutes=1),
    )
    async with AsyncSession(async_engine) as db:
        db.add_all(
            [
                ConversationMessage(
                    conversation_id=sources.annex.id,
                    role="user",
                    content="An annex answer",
                    created_at=now,
                ),
                ConversationMessage(
                    conversation_id=sources.main.id,
                    role="user",
                    content="An automated brief",
                    created_at=now,
                    hidden=True,
                ),
                ConversationMessage(
                    conversation_id=sources.main.id,
                    role="user",
                    content="A later topic",
                    created_at=now + timedelta(hours=1),
                ),
            ]
        )
        await db.flush()
        assert not await has_reply(db, opening)
        db.add(
            ConversationMessage(
                conversation_id=sources.main.id,
                role="user",
                content="The real answer",
                created_at=now,
            )
        )
        await db.flush()
        assert await has_reply(db, opening)
