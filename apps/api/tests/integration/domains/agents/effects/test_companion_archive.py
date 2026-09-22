"""Passive companion metadata round-trips through the real message JSONB column."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.api.archive_metadata import with_companion_metadata
from src.domains.agents.expressivity.activity_summary import ActivitySnapshot
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_delivered_tone_and_preparation_survive_archive_and_rollback(
    async_session: AsyncSession, test_user: User
) -> None:
    conversation = Conversation(user_id=test_user.id)
    async_session.add(conversation)
    await async_session.flush()
    activity: ActivitySnapshot = {
        "version": 1,
        "families": ["communicating"],
        "performed": [],
        "prepared": True,
        "failed": False,
    }
    metadata = with_companion_metadata(
        {"run_id": "archive-test"},
        {"register": "warm", "intensity": 0.5, "accent": "none"},
        activity,
    )
    row = ConversationMessage(
        conversation_id=conversation.id,
        role="assistant",
        content="A draft is ready.",
        message_metadata=metadata,
    )
    async_session.add(row)
    await async_session.commit()
    identity = row.id
    async_session.expire_all()
    kept = await async_session.get(ConversationMessage, identity)
    assert kept is not None and kept.message_metadata == metadata
    savepoint = await async_session.begin_nested()
    kept.message_metadata = {"companion_activity": {"performed": ["communicating"]}}
    await async_session.flush()
    await savepoint.rollback()
    await async_session.refresh(kept)
    assert kept.message_metadata == metadata
