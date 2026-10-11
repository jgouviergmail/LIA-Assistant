"""Saved-answer removal verifies its entire effect before one commit and exact post-ACK cleanup."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import authorize_actor, load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.bookmark_delete_schemas import (
    BookmarkDeleteInput,
    BookmarkDeleteObservation,
    BookmarkDeletePatch,
    canonical_bookmark_deletion,
)
from src.domains.agents.application.bookmark_delete_scope import observe_bookmark_deletion
from src.domains.agents.application.bookmark_delete_spec import BOOKMARK_DELETE_OPERATION
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.bookmarks.models import MessageBookmark
from src.domains.bookmarks.projection_deletion import require_owned_projection
from src.domains.bookmarks.service import BookmarkService
from src.domains.rag_spaces.document_deletion_cleanup import cleanup_deleted_document_file
from src.domains.rag_spaces.models import RAGChunk, RAGDocument
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


async def _access(db: AsyncSession, actor_id: UUID) -> None:
    await require_application_tools(db)
    await load_actor(db, actor_id)


async def prepare_bookmark_deletion(
    db: AsyncSession,
    actor_id: UUID,
    request: BookmarkDeleteInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    desired = BookmarkDeleteInput.model_validate(request.model_dump())
    await _access(db, actor_id)
    scope = await observe_bookmark_deletion(db, actor_id, desired)
    await _access(db, actor_id)
    return build_action_content(
        actor_id,
        BOOKMARK_DELETE_OPERATION,
        BookmarkDeletePatch(saved_answer_to_delete=scope),
        {"saved_answer_to_delete": scope.public_scope()},
        {"saved_answer_to_delete": scope.public_scope(after=True)},
        command_id=command_id,
    )


async def execute_bookmark_deletion(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != BOOKMARK_DELETE_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_bookmark_deletion(draft):
        raise CommandRejected("INVALID_INPUT")
    scope = BookmarkDeletePatch.model_validate(draft.intent).saved_answer_to_delete

    async def check() -> None:
        await _access(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    service = BookmarkService(db)
    await service.repository.lock_keep_owner(actor_id)
    authorize_actor(await UserRepository(db).get_by_id_for_preference_update(actor_id))
    await _lock_selection(db, actor_id, service, scope)
    if await observe_bookmark_deletion(db, actor_id, scope.request) != scope:
        raise CommandRejected("STALE_STATE")
    await service.remove(actor_id, scope.request.bookmark_id, commit=False)
    await _verify_removed(db, scope)
    await check()
    try:
        await db.commit()
    except (Exception, asyncio.CancelledError) as error:
        raise CommandRejected("COMPLETION_UNKNOWN") from error
    receipt.committed = True
    public = {**scope.public_scope(after=True), "removed": True, "file_cleanup_pending": False}
    receipt.values = {"saved_answer_to_delete": public}
    if scope.file is not None and scope.space_id is not None:
        public["file_cleanup_pending"] = True
        try:
            public["file_cleanup_pending"] = not await cleanup_deleted_document_file(
                actor_id, scope.space_id, scope.file.stored_filename, scope.file.file_digest
            )
        except (Exception, asyncio.CancelledError) as error:
            logger.warning("bookmark_file_cleanup_pending", error_type=type(error).__name__)


async def _lock_selection(
    db: AsyncSession, actor_id: UUID, service: BookmarkService, scope: BookmarkDeleteObservation
) -> None:
    row = await service.repository.get_for_user(actor_id, scope.request.bookmark_id)
    if row is None:
        raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED")
    if scope.projection is not None:
        document = await db.scalar(select(RAGDocument).where(RAGDocument.id == scope.projection.id))
        if document is None:
            raise CommandRejected("STALE_STATE")
        await require_owned_projection(db, row, document)
        await db.execute(
            select(RAGChunk.id)
            .where(RAGChunk.document_id == document.id)
            .order_by(RAGChunk.id)
            .with_for_update()
        )
    await db.execute(
        select(MessageBookmark.id)
        .where(MessageBookmark.id == row.id, MessageBookmark.user_id == actor_id)
        .with_for_update()
    )


async def _verify_removed(db: AsyncSession, scope: BookmarkDeleteObservation) -> None:
    if (
        await db.scalar(
            select(MessageBookmark.id).where(MessageBookmark.id == scope.request.bookmark_id)
        )
        is not None
    ):
        raise CommandRejected("STALE_STATE")
    if scope.projection is not None:
        remaining = await db.scalar(
            select(func.count(RAGChunk.id)).where(RAGChunk.document_id == scope.projection.id)
        )
        document_id = await db.scalar(
            select(RAGDocument.id).where(RAGDocument.id == scope.projection.id)
        )
        if remaining or document_id is not None:
            raise CommandRejected("STALE_STATE")
