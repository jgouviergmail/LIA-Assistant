"""Source-owned archive selection and bounded transfer from exact frozen file descriptors."""

import hashlib
import json
import zipfile
from contextlib import AsyncExitStack
from pathlib import Path
from tempfile import SpooledTemporaryFile
from uuid import UUID

from pydantic import JsonValue, TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import RAG_SPACES_ARCHIVE_MISSING_MEMBER
from src.core.exceptions import ResourceConflictError
from src.domains.rag_spaces.archive_names import archive_name_reservations, unique_archive_name
from src.domains.rag_spaces.archive_schemas import ArchiveDocumentSnapshot, DocumentArchiveSnapshot
from src.domains.rag_spaces.document_access import document_file_path, raise_document_not_found
from src.domains.rag_spaces.document_ops import raise_archive_too_large
from src.domains.rag_spaces.models import RAGDocument
from src.domains.rag_spaces.ui_queries import owned_space
from src.infrastructure.file_transfer import LocalFileRead

_ROW = TypeAdapter(dict[str, JsonValue])


async def _close_readers(readers: list[tuple[str, LocalFileRead]]) -> None:
    """Every descriptor is closed even when another close is cancelled or fails."""
    stack = AsyncExitStack()
    for _, reader in readers:
        stack.push_async_callback(reader.close)
    await stack.aclose()


def _source_file(document: RAGDocument) -> LocalFileRead | None:
    try:
        path = document_file_path(document)
        return LocalFileRead.open(path)
    except FileNotFoundError:
        return None
    except OSError, ValueError, RuntimeError:
        raise_document_not_found(document.id)


async def _selection(
    db: AsyncSession, actor_id: UUID, space_id: UUID, ids: tuple[UUID, ...]
) -> tuple[DocumentArchiveSnapshot, list[tuple[str, LocalFileRead]]]:
    space = await owned_space(db, actor_id, space_id)
    rows = (
        await db.execute(
            select(RAGDocument, func.to_jsonb(RAGDocument.__table__.table_valued()))
            .where(
                RAGDocument.id.in_(ids),
                RAGDocument.space_id == space_id,
                RAGDocument.user_id == actor_id,
            )
            .execution_options(populate_existing=True)
        )
    ).all()
    by_id = {document.id: (document, raw) for document, raw in rows}
    if len(by_id) != len(ids):
        raise_document_not_found(next(identifier for identifier in ids if identifier not in by_id))
    if (
        sum(document.file_size for document, _ in rows)
        > settings.rag_spaces_archive_max_mb * 1024 * 1024
    ):
        raise_archive_too_large(settings.rag_spaces_archive_max_mb)
    taken = archive_name_reservations()
    selected: list[ArchiveDocumentSnapshot] = []
    readers: list[tuple[str, LocalFileRead]] = []
    try:
        for identifier in ids:
            document, raw = by_id[identifier]
            name = unique_archive_name(document.original_filename, taken)
            reader = _source_file(document)
            if reader is not None:
                readers.append((name, reader))
                if reader.file_size_bytes != document.file_size:
                    raise ResourceConflictError("archive", detail={"error_code": "STALE_STATE"})
            digest = hashlib.sha256(
                json.dumps(
                    _ROW.validate_python(raw),
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            selected.append(
                ArchiveDocumentSnapshot(
                    document_id=identifier,
                    original_filename=document.original_filename,
                    member_name=name,
                    file_size_bytes=document.file_size,
                    present=reader is not None,
                    file_digest=reader.identity_digest if reader else None,
                    source_digest=digest,
                )
            )
        return (
            DocumentArchiveSnapshot(
                space_id=space_id, space_name=space.name, documents=tuple(selected)
            ),
            readers,
        )
    except BaseException:
        await _close_readers(readers)
        raise


async def read_owned_archive_snapshot(
    db: AsyncSession, actor_id: UUID, space_id: UUID, ids: tuple[UUID, ...]
) -> DocumentArchiveSnapshot:
    selected, readers = await _selection(db, actor_id, space_id, ids)
    try:
        return selected
    finally:
        await _close_readers(readers)


async def open_owned_document_archive(
    db: AsyncSession, actor_id: UUID, expected: DocumentArchiveSnapshot
) -> LocalFileRead:
    selected, readers = await _selection(
        db,
        actor_id,
        expected.space_id,
        tuple(document.document_id for document in expected.documents),
    )
    output = SpooledTemporaryFile[bytes](max_size=512 * 1024, mode="w+b")
    try:
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            try:
                if selected != expected:
                    raise ResourceConflictError("archive", detail={"error_code": "STALE_STATE"})
                for name, reader in readers:
                    await reader.freeze(max_bytes=reader.file_size_bytes)
                    with archive.open(name, "w") as member:
                        await reader.copy_to(member)
                missing = [
                    document.member_name for document in selected.documents if not document.present
                ]
                if missing:
                    archive.writestr(RAG_SPACES_ARCHIVE_MISSING_MEMBER, "\n".join(missing) + "\n")
            finally:
                await _close_readers(readers)
        output.seek(0)
        return LocalFileRead(output, Path("approved-archive.zip"))
    except BaseException:
        output.close()
        raise
