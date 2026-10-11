"""Owned exact document subset, local file metadata and streaming private SQL witnesses."""

import hashlib
import json
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.document_delete_schemas import (
    DocumentDeleteFile,
    DocumentDeleteInput,
    DocumentDeleteSelection,
)
from src.domains.agents.application.space_delete_schemas import SpaceDeleteDocument
from src.domains.agents.application.space_update_schemas import SpaceUpdateTarget
from src.domains.rag_spaces.document_access import (
    document_file_path,
    raise_document_not_found,
    require_deletable_document,
)
from src.domains.rag_spaces.models import RAGChunk, RAGDocument, RAGDriveSource, RAGMailSource
from src.domains.rag_spaces.ui_queries import owned_space
from src.infrastructure.file_transfer import LocalFileRead


async def _file_scope(document: RAGDocument) -> DocumentDeleteFile:
    try:
        reader = LocalFileRead.open(document_file_path(document))
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


async def _private_digest(
    db: AsyncSession,
    ids: tuple[UUID, ...],
    *,
    normalized_space_id: UUID | None = None,
    ignore_updated_at: bool = False,
) -> str:
    digest = hashlib.sha256()
    statements = (
        select(func.to_jsonb(RAGDocument.__table__.table_valued()))
        .where(RAGDocument.id.in_(ids))
        .order_by(RAGDocument.id),
        select(func.to_jsonb(RAGChunk.__table__.table_valued()))
        .where(RAGChunk.document_id.in_(ids))
        .order_by(RAGChunk.id),
    )
    for index, statement in enumerate(statements):
        digest.update(bytes([index]))
        rows = await db.stream_scalars(statement.execution_options(yield_per=32))
        try:
            async for row in rows:
                row = dict(row)
                if normalized_space_id is not None:
                    row["space_id"] = str(normalized_space_id)
                if ignore_updated_at:
                    row.pop("updated_at", None)
                encoded = json.dumps(
                    row, sort_keys=True, ensure_ascii=False, separators=(",", ":")
                ).encode("utf-8")
                if len(encoded) > 64_000:
                    raise ValueError("Document witness row too large for exact deletion")
                digest.update(len(encoded).to_bytes(8, "big"))
                digest.update(encoded)
        finally:
            await rows.close()
    return digest.hexdigest()


async def document_deletion_selection(
    db: AsyncSession, actor_id: UUID, request: DocumentDeleteInput
) -> DocumentDeleteSelection:
    space = await owned_space(db, actor_id, request.space_id)
    documents = list(
        (
            await db.scalars(
                select(RAGDocument)
                .where(
                    RAGDocument.id.in_(request.document_ids),
                    RAGDocument.space_id == space.id,
                    RAGDocument.user_id == actor_id,
                )
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    by_id = {document.id: document for document in documents}
    if len(by_id) != len(request.document_ids):
        raise_document_not_found(
            next(identifier for identifier in request.document_ids if identifier not in by_id)
        )
    _validate_documents(documents)
    await check_linked_sources(db, actor_id, documents)
    chunk_owners = await db.scalar(
        select(func.count(RAGChunk.id)).where(
            RAGChunk.document_id.in_(request.document_ids),
            or_(
                RAGChunk.user_id.is_distinct_from(actor_id),
                RAGChunk.space_id.is_distinct_from(space.id),
            ),
        )
    )
    if chunk_owners:
        raise CommandRejected("FORBIDDEN")
    files = [await _file_scope(by_id[identifier]) for identifier in request.document_ids]
    selected = DocumentDeleteSelection(
        request=request,
        space=SpaceUpdateTarget.model_validate(space),
        items=tuple(
            SpaceDeleteDocument.model_validate(by_id[identifier])
            for identifier in request.document_ids
        ),
        chunks=int(
            await db.scalar(
                select(func.count(RAGChunk.id)).where(
                    RAGChunk.document_id.in_(request.document_ids)
                )
            )
            or 0
        ),
        space_documents=int(
            await db.scalar(
                select(func.count(RAGDocument.id)).where(RAGDocument.space_id == space.id)
            )
            or 0
        ),
        state_digest=await _private_digest(db, request.document_ids),
        files=tuple(files),
    )
    if len(selected.model_dump_json().encode("utf-8")) > 64_000:
        raise ValueError("Deletion selection too large; select fewer documents")
    return selected


def _validate_documents(documents: list[RAGDocument]) -> None:
    if any(document.status in {"processing", "reindexing"} for document in documents):
        raise CommandRejected("BUSY")
    for document in documents:
        require_deletable_document(document)


async def check_linked_sources(
    db: AsyncSession, actor_id: UUID, documents: list[RAGDocument], *, lock: bool = False
) -> None:
    for model, identities in (
        (
            RAGDriveSource,
            {document.drive_source_id for document in documents if document.drive_source_id},
        ),
        (
            RAGMailSource,
            {document.mail_source_id for document in documents if document.mail_source_id},
        ),
    ):
        if not identities:
            continue
        statement = (
            select(model)
            .where(
                model.id.in_(identities),
                model.user_id == actor_id,
                model.space_id == documents[0].space_id,
            )
            .order_by(model.id)
            .execution_options(populate_existing=True)
        )
        if lock:
            statement = statement.with_for_update()
        sources = list((await db.scalars(statement)).all())
        if len(sources) != len(identities):
            raise CommandRejected("FORBIDDEN")
        if any(source.sync_status == "syncing" for source in sources):
            raise CommandRejected("BUSY")


async def lock_document_deletion(
    db: AsyncSession, actor_id: UUID, request: DocumentDeleteInput
) -> None:
    documents = list(
        (
            await db.scalars(
                select(RAGDocument)
                .where(
                    RAGDocument.id.in_(request.document_ids),
                    RAGDocument.space_id == request.space_id,
                    RAGDocument.user_id == actor_id,
                )
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    await check_linked_sources(db, actor_id, documents, lock=True)
    await db.execute(
        select(RAGDocument.id)
        .where(
            RAGDocument.id.in_(request.document_ids),
            RAGDocument.user_id == actor_id,
            RAGDocument.space_id == request.space_id,
        )
        .order_by(RAGDocument.id)
        .with_for_update()
    )
