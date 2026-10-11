"""Native consent and execution observe through the existing exact answer-copy builder."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.bookmark_keep_schemas import (
    BookmarkKeepInput,
    BookmarkKeepObservation,
    ResolvedBookmarkKeepInput,
)
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.effects.digest import payload_digest
from src.domains.bookmarks.models import MessageBookmark
from src.domains.bookmarks.service import BookmarkService


def bookmark_copy_digest(row: MessageBookmark) -> str:
    return payload_digest(
        {
            "user_id": str(row.user_id),
            "message_id": str(row.message_id),
            "conversation_id": str(row.conversation_id),
            "content": row.content,
            "request_content": row.request_content,
            "answered_at": row.answered_at.isoformat(),
            "run_id": row.run_id,
        }
    )


async def observe_bookmark_keep(
    db: AsyncSession, actor_id: UUID, request: ResolvedBookmarkKeepInput
) -> BookmarkKeepObservation:
    service = BookmarkService(db)
    existing = await service.repository.get_by_message(actor_id, request.message_id)
    row = existing or await service.copy_owned_answer(actor_id, request.message_id)
    count = await service.repository.count_for_user(actor_id)
    maximum = settings.bookmarks_max_per_user
    if existing is None and count >= maximum:
        raise CommandRejected("CONSTRAINT_VIOLATION")
    return BookmarkKeepObservation(
        request=request,
        conversation_id=row.conversation_id,
        answered_at=row.answered_at,
        answer_preview=row.content[:300],
        request_preview=row.request_content[:300] if row.request_content is not None else None,
        answer_chars=len(row.content),
        request_chars=len(row.request_content) if row.request_content is not None else None,
        existing_id=existing.id if existing is not None else None,
        kept_count=count,
        max_per_user=maximum,
        copy_digest=bookmark_copy_digest(row),
    )


async def resolve_bookmark_keep(
    db: AsyncSession, actor_id: UUID, request: BookmarkKeepInput
) -> ResolvedBookmarkKeepInput:
    identity = request.message_id
    if identity is None:
        message = await BookmarkService(db).repository.latest_visible_assistant_message(actor_id)
        if message is None:
            raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED")
        identity = message.id
    return ResolvedBookmarkKeepInput(message_id=identity)
