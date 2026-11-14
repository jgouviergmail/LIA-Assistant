"""Selection resolution never infers a thread from recent activity or client state."""

from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversation_selection import ConversationSelection
from src.core.conversation_target import ConversationKind
from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.domains.conversations.catalogue_service import ConversationCatalogueService
from src.domains.conversations.models import Conversation
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_an_empty_main_read_has_no_creation_side_effect(
    async_session: AsyncSession, test_user: User
) -> None:
    service = ConversationCatalogueService(async_session)
    assert await service.resolve_target(test_user.id, ConversationSelection()) is None
    assert (
        await async_session.scalar(
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.user_id == test_user.id)
        )
        == 0
    )
    main = await service.resolve_target(test_user.id, ConversationSelection(), create_primary=True)
    assert main is not None and main.kind == ConversationKind.MAIN
    assert await service.resolve_target(test_user.id, ConversationSelection()) == main


async def test_explicit_annex_stays_annex_while_legacy_omission_stays_main(
    async_session: AsyncSession, test_user: User
) -> None:
    service = ConversationCatalogueService(async_session)
    main = await service.ensure_primary(test_user.id)
    annex = Conversation(user_id=test_user.id, kind=ConversationKind.SECONDARY, title="Annex")
    async_session.add(annex)
    await async_session.flush()
    selected = await service.resolve_target(
        test_user.id,
        ConversationSelection(
            conversation_id=annex.id,
            conversation_revision=annex.revision,
        ),
    )
    assert selected is not None and selected.id == annex.id
    assert await service.resolve_target(test_user.id, ConversationSelection()) == main


async def test_request_prepared_before_reset_cannot_join_the_new_generation(
    async_session: AsyncSession, test_user: User
) -> None:
    service = ConversationCatalogueService(async_session)
    before = await service.ensure_primary(test_user.id)
    after = replace(before, revision=before.revision + 1, runtime_id=uuid4())
    await async_session.execute(
        update(Conversation)
        .where(Conversation.id == before.id)
        .values(
            revision=after.revision,
            runtime_id=after.runtime_id,
        )
    )
    with pytest.raises(ResourceConflictError) as failure:
        await service.resolve_target(
            test_user.id,
            ConversationSelection(
                conversation_id=before.id,
                conversation_revision=before.revision,
            ),
        )
    assert failure.value.status_code == 409
    assert await service.resolve_target(test_user.id, ConversationSelection()) == after


@pytest.mark.parametrize("foreign_exists", [False, True])
async def test_private_targets_are_neither_selected_nor_disclosed(
    async_session: AsyncSession, test_user: User, foreign_exists: bool
) -> None:
    identity = uuid4()
    if foreign_exists:
        foreign = User(email=f"other-{uuid4()}@example.test", is_active=True)
        async_session.add(foreign)
        await async_session.flush()
        async_session.add(Conversation(id=identity, user_id=foreign.id))
        await async_session.flush()
    with pytest.raises(ResourceNotFoundError) as failure:
        await ConversationCatalogueService(async_session).resolve_target(
            test_user.id, ConversationSelection(conversation_id=identity, conversation_revision=0)
        )
    assert failure.value.status_code == 404
