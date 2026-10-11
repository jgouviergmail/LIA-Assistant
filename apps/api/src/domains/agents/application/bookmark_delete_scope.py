"""Observe owned saved-copy/projection state without reindexing or exposing stored paths."""

from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.bookmark_delete_schemas import (
    BookmarkDeleteInput,
    BookmarkDeleteObservation,
)
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.document_delete_schemas import DocumentDeleteFile
from src.domains.agents.application.document_delete_scope import _private_digest
from src.domains.agents.application.space_delete_schemas import SpaceDeleteDocument
from src.domains.agents.effects.digest import payload_digest
from src.domains.bookmarks.projection_deletion import require_owned_projection
from src.domains.bookmarks.repository import BookmarkRepository
from src.domains.rag_spaces.models import RAGChunk, RAGDocument
from src.infrastructure.file_transfer import LocalFileRead


async def _file(document: RAGDocument) -> DocumentDeleteFile:
    root = Path(settings.rag_spaces_storage_path).resolve()
    account = root / str(document.user_id)
    space = account / str(document.space_id)
    path = space / document.filename
    if account.is_symlink() or space.is_symlink() or path.is_symlink():
        raise CommandRejected("INVALID_INPUT")
    if space.resolve() != space or path.resolve().parent != space or path.name != document.filename:
        raise CommandRejected("INVALID_INPUT")
    try:
        reader = await LocalFileRead.async_open(path)
    except FileNotFoundError:
        return DocumentDeleteFile(document_id=document.id, stored_filename=document.filename)
    except OSError, ValueError, RuntimeError:
        raise CommandRejected("INVALID_INPUT") from None
    try:
        return DocumentDeleteFile(
            document_id=document.id,
            stored_filename=document.filename,
            file_digest=reader.identity_digest,
        )
    finally:
        await reader.close()


async def observe_bookmark_deletion(
    db: AsyncSession, actor_id: UUID, request: BookmarkDeleteInput
) -> BookmarkDeleteObservation:
    row = await BookmarkRepository(db).get_for_user(actor_id, request.bookmark_id)
    if row is None:
        raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED")
    document = None
    if row.rag_document_id is not None:
        document = await db.scalar(
            select(RAGDocument)
            .where(RAGDocument.id == row.rag_document_id)
            .execution_options(populate_existing=True)
        )
        if document is None:
            raise CommandRejected("STALE_STATE")
        await require_owned_projection(db, row, document, lock=False)
        if document.status in {"processing", "reindexing"}:
            raise CommandRejected("BUSY")
    raw = await db.scalar(
        select(func.to_jsonb(row.__table__.table_valued())).where(row.__table__.c.id == row.id)
    )
    chunks = 0
    projection_digest = None
    file = None
    if document is not None:
        chunks = int(
            await db.scalar(
                select(func.count(RAGChunk.id)).where(RAGChunk.document_id == document.id)
            )
            or 0
        )
        if chunks > 5_000:
            raise CommandRejected("CONSTRAINT_VIOLATION")
        projection_digest = await _private_digest(db, (document.id,))
        file = await _file(document)
    return BookmarkDeleteObservation(
        request=request,
        answered_at=row.answered_at,
        answer_preview=row.content[:300],
        request_preview=row.request_content[:300] if row.request_content is not None else None,
        answer_chars=len(row.content),
        request_chars=len(row.request_content) if row.request_content is not None else None,
        projection=SpaceDeleteDocument.model_validate(document) if document is not None else None,
        space_id=document.space_id if document is not None else None,
        chunks=chunks,
        state_digest=payload_digest({"bookmark": raw, "projection": projection_digest}),
        file=file,
    )
