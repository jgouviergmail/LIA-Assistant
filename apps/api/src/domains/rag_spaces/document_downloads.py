"""Existing document ownership/path rules provide exact local download snapshots."""

import hashlib
import json
from uuid import UUID

from pydantic import JsonValue, TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.rag_spaces import ui_queries
from src.domains.rag_spaces.document_access import document_file_path, raise_document_not_found
from src.domains.rag_spaces.download_schemas import DocumentDownloadSnapshot
from src.domains.rag_spaces.models import RAGDocument
from src.infrastructure.file_transfer import LocalFileRead

_ROW = TypeAdapter(dict[str, JsonValue])


async def _snapshot(
    db: AsyncSession, actor_id: UUID, space_id: UUID, document_id: UUID
) -> tuple[DocumentDownloadSnapshot, LocalFileRead]:
    space = await ui_queries.owned_space(db, actor_id, space_id)
    document: RAGDocument | None = await db.scalar(
        select(RAGDocument)
        .where(
            RAGDocument.id == document_id,
            RAGDocument.space_id == space_id,
            RAGDocument.user_id == actor_id,
        )
        .execution_options(populate_existing=True)
    )
    if document is None:
        raise_document_not_found(document_id)
    raw = _ROW.validate_python(
        await db.scalar(
            select(func.to_jsonb(RAGDocument.__table__.table_valued())).where(
                RAGDocument.id == document_id
            )
        )
    )
    try:
        reader = LocalFileRead.open(document_file_path(document))
    except OSError, ValueError, RuntimeError:
        raise_document_not_found(document_id)
    try:
        if reader.file_size_bytes != document.file_size:
            raise ResourceConflictError("document", detail={"error_code": "STALE_STATE"})
        digest = hashlib.sha256(
            json.dumps(raw, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        selected = DocumentDownloadSnapshot(
            space_id=space_id,
            document_id=document_id,
            space_name=space.name,
            original_filename=document.original_filename,
            content_type=document.content_type,
            file_size_bytes=reader.file_size_bytes,
            file_digest=reader.identity_digest,
            source_digest=digest,
        )
        return selected, reader
    except BaseException:
        await reader.close()
        raise


async def read_owned_document_snapshot(
    db: AsyncSession, actor_id: UUID, space_id: UUID, document_id: UUID
) -> DocumentDownloadSnapshot:
    selected, reader = await _snapshot(db, actor_id, space_id, document_id)
    try:
        return selected
    finally:
        await reader.close()


async def open_owned_document_download(
    db: AsyncSession, actor_id: UUID, expected: DocumentDownloadSnapshot | dict[str, JsonValue]
) -> LocalFileRead:
    selected = DocumentDownloadSnapshot.model_validate(expected)
    current, reader = await _snapshot(db, actor_id, selected.space_id, selected.document_id)
    if current != selected:
        await reader.close()
        raise ResourceConflictError("document", detail={"error_code": "STALE_STATE"})
    return reader
