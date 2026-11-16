"""The return of an act publishes in the generation it began in, else in Main (2026-11-14).

A call placed from an annex returned to Main: every notification resolved
« the current Main » at publication. The return now names its origin — the
discussion and the generation the act began in — and the publication checks,
under the same locks as Main, that this generation still lives. A reset or a
deletion either commits first, and the return goes to Main, or waits for the
publication and retires the generation with the return inside.
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.conversation_publication import OriginPublication, return_publication
from src.core.conversation_target import ConversationOrigin
from src.domains.conversations.models import Conversation
from src.domains.conversations.publication_repository import ConversationPublicationRepository
from src.domains.conversations.service import ConversationService
from tests.fixtures.persisted_runtimes import persist_annex_with_main as _annex_and_main

pytestmark = pytest.mark.integration


async def _publish(engine: AsyncEngine, owner_id: UUID, origin: ConversationOrigin) -> UUID:
    async with AsyncSession(engine) as db:
        message = await ConversationService().archive_message(
            OriginPublication(owner_id, origin), "assistant", "A call's return", None, db
        )
        published = message.conversation_id
        await db.commit()
        return published


async def test_a_return_publishes_in_the_annex_its_act_began_in(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    annex, _main = await _annex_and_main(async_engine, committed_user_ids)
    async with AsyncSession(async_engine) as db:
        message = await ConversationService().archive_message(
            OriginPublication(annex.owner_id, ConversationOrigin.of(annex)),
            "assistant",
            "A call's return",
            None,
            db,
        )
        assert message.conversation_id == annex.id
        assert message.message_metadata == {"conversation_revision": annex.revision}
        await db.commit()


async def test_a_reset_since_the_act_sends_the_return_to_main(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    annex, main_id = await _annex_and_main(async_engine, committed_user_ids)
    async with AsyncSession(async_engine) as db:
        await db.execute(
            update(Conversation)
            .where(Conversation.id == annex.id)
            .values(revision=annex.revision + 1, runtime_id=uuid4())
        )
        await db.commit()
    published = await _publish(async_engine, annex.owner_id, ConversationOrigin.of(annex))
    assert published == main_id


async def test_a_deleted_annex_sends_the_return_to_main(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    annex, main_id = await _annex_and_main(async_engine, committed_user_ids)
    async with AsyncSession(async_engine) as db:
        await db.execute(
            update(Conversation).where(Conversation.id == annex.id).values(deleted_at=text("now()"))
        )
        await db.commit()
    published = await _publish(async_engine, annex.owner_id, ConversationOrigin.of(annex))
    assert published == main_id


async def test_an_origin_of_another_account_is_never_written_to(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    mine, my_main = await _annex_and_main(async_engine, committed_user_ids)
    theirs, _their_main = await _annex_and_main(async_engine, committed_user_ids)
    published = await _publish(async_engine, mine.owner_id, ConversationOrigin.of(theirs))
    assert published == my_main


async def test_an_act_begun_in_main_returns_to_main(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    annex, main_id = await _annex_and_main(async_engine, committed_user_ids)
    published = await _publish(async_engine, annex.owner_id, ConversationOrigin(main_id, 2))
    assert published == main_id
    # Main reset since the act: still the current Main, never an error.
    published = await _publish(async_engine, annex.owner_id, ConversationOrigin(main_id, 1))
    assert published == main_id


async def test_no_origin_is_the_current_main(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    annex, main_id = await _annex_and_main(async_engine, committed_user_ids)
    async with AsyncSession(async_engine) as db:
        message = await ConversationService().archive_message(
            return_publication(annex.owner_id, None), "assistant", "A reminder", None, db
        )
        assert message.conversation_id == main_id
        await db.commit()


async def test_the_publication_holds_the_generation_until_it_commits(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    """A reset cannot slip between the check and the archive: it waits for the commit."""
    annex, _main = await _annex_and_main(async_engine, committed_user_ids)
    async with AsyncSession(async_engine) as publisher, AsyncSession(async_engine) as resetter:
        await ConversationService().archive_message(
            OriginPublication(annex.owner_id, ConversationOrigin.of(annex)),
            "assistant",
            "A call's return",
            None,
            publisher,
        )
        with pytest.raises(DBAPIError):
            await resetter.execute(
                select(Conversation.id)
                .where(Conversation.id == annex.id)
                .with_for_update(nowait=True)
            )
        await resetter.rollback()
        await publisher.commit()
        locked = await resetter.scalar(
            select(Conversation.id).where(Conversation.id == annex.id).with_for_update(nowait=True)
        )
        assert locked == annex.id
        await resetter.rollback()


async def test_a_notification_links_to_the_annex_only_while_its_generation_lives(
    async_engine: AsyncEngine, committed_user_ids: list[UUID]
) -> None:
    annex, main_id = await _annex_and_main(async_engine, committed_user_ids)
    async with AsyncSession(async_engine) as db:
        repository = ConversationPublicationRepository(db)
        assert await repository.secondary_origin(annex.owner_id, ConversationOrigin.of(annex)) == (
            annex.id
        )
        # Main is never linked: its view reads every notification without coordinates.
        assert await repository.secondary_origin(
            annex.owner_id, ConversationOrigin(main_id, 2)
        ) is (None)
        # A generation since retired, or another account's annex, names nothing.
        stale = ConversationOrigin(annex.id, annex.revision - 1)
        assert await repository.secondary_origin(annex.owner_id, stale) is None
        assert await repository.secondary_origin(uuid4(), ConversationOrigin.of(annex)) is None
