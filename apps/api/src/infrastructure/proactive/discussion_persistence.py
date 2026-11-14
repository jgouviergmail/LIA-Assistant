"""Composition of atomic discussion persistence and the existing chat archive."""

from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversation_publication import CurrentPrimaryPublication
from src.domains.conversations.service import ConversationService
from src.domains.proactive_discussions.publication_repository import DiscussionPublicationRepository
from src.domains.shared.discussion_archive import ArchivedDiscussion


async def archive_discussion(
    db: AsyncSession, *, owner_id: UUID, content: str, metadata: dict[str, JsonValue]
) -> ArchivedDiscussion:
    """Archive an opening as an assistant message of the person's active conversation.

    Args:
        db: The session to write with.
        owner_id: The account.
        content: The opening's words.
        metadata: The message metadata.

    Returns:
        The archived message and its conversation.

    Raises:
        ResourceNotFoundError: The person has no active conversation.
    """
    message = await ConversationService().archive_message(
        conversation_id=CurrentPrimaryPublication(owner_id),
        role="assistant",
        content=content,
        metadata=metadata,
        db=db,
    )
    return ArchivedDiscussion(conversation_id=message.conversation_id, message_id=message.id)


def publication_repository(db: AsyncSession) -> DiscussionPublicationRepository:
    """Build the publication repository on the chat archive.

    Args:
        db: The session to write with.

    Returns:
        The repository.
    """
    return DiscussionPublicationRepository(db, archive_discussion)
