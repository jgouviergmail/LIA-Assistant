"""A saved-answer transfer shares full export bytes, owner/consent checks and the original browser seam."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.bookmark_download_schemas import (
    BookmarkDownloadInput,
    BookmarkDownloadPatch,
    BookmarkDownloadSnapshot,
    canonical_bookmark_download,
)
from src.domains.agents.application.bookmark_download_spec import BOOKMARK_DOWNLOAD_OPERATION
from src.domains.agents.application.bookmark_keep_scope import bookmark_copy_digest
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.management_export import authorize_management_export
from src.domains.agents.application.stored_download_service import StoredDownload
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.agents.effects.digest import payload_digest
from src.domains.bookmarks.export import BookmarkExport, export_bookmark
from src.domains.bookmarks.models import MessageBookmark
from src.domains.bookmarks.repository import BookmarkRepository
from src.infrastructure.file_transfer import LocalFileRead


async def _snapshot(
    db: AsyncSession, actor_id: UUID, request: BookmarkDownloadInput, *, lock: bool = False
) -> tuple[BookmarkDownloadSnapshot, BookmarkExport]:
    actor = await load_actor(db, actor_id)
    if lock:
        await db.execute(
            select(MessageBookmark.id)
            .where(MessageBookmark.id == request.bookmark_id, MessageBookmark.user_id == actor_id)
            .with_for_update()
        )
    row = await BookmarkRepository(db).get_for_user(actor_id, request.bookmark_id)
    if row is None:
        raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED")
    exported = export_bookmark(row, actor)
    scope = BookmarkDownloadSnapshot(
        request=request,
        answered_at=row.answered_at,
        answer_preview=row.content[:300],
        request_preview=row.request_content[:300] if row.request_content is not None else None,
        filename=exported.filename,
        file_bytes=len(exported.data),
        state_digest=payload_digest({"copy": bookmark_copy_digest(row), "export": exported.digest}),
    )
    return scope, exported


async def prepare_bookmark_download(
    db: AsyncSession,
    actor_id: UUID,
    request: BookmarkDownloadInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    context = runtime_context_if_running()
    if context is None or context.user_id != actor_id:
        raise CommandRejected("FORBIDDEN")
    await authorize_management_export(db, actor_id, context.application_origin)
    scope, _ = await _snapshot(
        db, actor_id, BookmarkDownloadInput.model_validate(request.model_dump())
    )
    await authorize_management_export(db, actor_id, context.application_origin)
    return build_action_content(
        actor_id,
        BOOKMARK_DOWNLOAD_OPERATION,
        BookmarkDownloadPatch(saved_answer_to_download=scope),
        {"saved_answer_to_download": None},
        {"saved_answer_to_download": scope.public_scope()},
        command_id=command_id,
    )


async def open_bookmark_download(
    db: AsyncSession, actor_id: UUID, draft: ApplicationActionDraftContent
) -> StoredDownload:
    if draft.actor_id != actor_id or draft.operation_id != BOOKMARK_DOWNLOAD_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_bookmark_download(draft):
        raise CommandRejected("INVALID_INPUT")
    expected = BookmarkDownloadPatch.model_validate(draft.intent).saved_answer_to_download
    actual, exported = await _snapshot(db, actor_id, expected.request, lock=True)
    if actual != expected:
        raise CommandRejected("STALE_STATE")
    reader = await LocalFileRead.async_from_bytes(exported.data)
    return StoredDownload(
        reader,
        actual.filename,
        actual.content_type,
        {"bookmark_id": str(expected.request.bookmark_id)},
    )
