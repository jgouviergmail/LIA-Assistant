"""An implicit keep resolves the answer in the originating discussion only."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.run_authority import run_authority_scope
from src.domains.agents.application.bookmark_keep_schemas import BookmarkKeepInput
from src.domains.agents.application.bookmark_keep_scope import resolve_bookmark_keep
from src.domains.agents.application.command_service import CommandRejected
from src.domains.conversations.models import ConversationMessage
from tests.fixtures.learning_sources import Sources, source_authority
from tests.fixtures.learning_sources import sources as sources

pytestmark = pytest.mark.integration


async def test_keep_does_not_take_a_newer_answer_from_another_discussion(
    async_engine: AsyncEngine, sources: Sources
) -> None:
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        annex = ConversationMessage(
            conversation_id=sources.annex.id,
            role="assistant",
            content="Keep this annex answer",
            created_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        db.add_all(
            [
                annex,
                ConversationMessage(
                    conversation_id=sources.main.id, role="assistant", content="Newer main answer"
                ),
            ]
        )
        await db.commit()
        with run_authority_scope(source_authority(sources.annex)):
            result = await resolve_bookmark_keep(db, sources.main.owner_id, BookmarkKeepInput())
        assert result.message_id == annex.id


async def test_keep_without_an_explicit_message_or_bound_source_refuses(
    async_engine: AsyncEngine, sources: Sources
) -> None:
    async with AsyncSession(async_engine) as db:
        db.add(
            ConversationMessage(
                conversation_id=sources.main.id, role="assistant", content="Unrelated answer"
            )
        )
        await db.commit()
        with pytest.raises(CommandRejected):
            await resolve_bookmark_keep(db, sources.main.owner_id, BookmarkKeepInput())
