"""Source movement refusals, exact personal space capacity and normalized SQL postcondition."""

import os
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.document_delete_schemas import DocumentDeleteInput
from src.domains.agents.application.document_delete_scope import (
    _private_digest,
    document_deletion_selection,
)
from src.domains.agents.application.document_move_schemas import (
    DocumentMoveInput,
    DocumentMoveSelection,
)
from src.domains.agents.application.space_update import _source_row
from src.domains.agents.application.space_update_schemas import SpaceUpdateTarget
from src.domains.agents.effects.digest import payload_digest
from src.domains.rag_spaces.document_access import raise_document_managed
from src.domains.rag_spaces.document_move_files import _path
from src.domains.rag_spaces.document_ops import document_move_refusal
from src.domains.rag_spaces.models import RAGChunk, RAGDocument
from src.domains.rag_spaces.reindex import get_reindex_status
from src.domains.rag_spaces.ui_queries import owned_space


async def require_move_idle() -> None:
    if (await get_reindex_status()).get("in_progress"):
        raise CommandRejected("BUSY")


async def document_move_selection(
    db: AsyncSession, actor_id: UUID, request: DocumentMoveInput
) -> DocumentMoveSelection:
    await require_move_idle()
    selected = await document_deletion_selection(
        db,
        actor_id,
        DocumentDeleteInput(space_id=request.space_id, document_ids=request.document_ids),
    )
    source = await owned_space(db, actor_id, request.space_id)
    target = await owned_space(db, actor_id, request.target_space_id)
    documents = list(
        (
            await db.scalars(
                select(RAGDocument)
                .where(
                    RAGDocument.id.in_(request.document_ids),
                    RAGDocument.user_id == actor_id,
                    RAGDocument.space_id == source.id,
                )
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    if len(documents) != len(request.document_ids):
        raise CommandRejected("STALE_STATE")
    for document in documents:
        refusal = document_move_refusal(document, source, target)
        if refusal == "document_busy":
            raise CommandRejected("BUSY")
        if refusal is not None:
            raise_document_managed(document.source_type)
        if os.path.lexists(_path(actor_id, target.id, document.filename)):
            raise CommandRejected("STALE_STATE")
    if source.serving_embedding_model or target.serving_embedding_model:
        raise CommandRejected("BUSY")
    if await db.scalar(
        select(func.count(RAGChunk.id)).where(
            RAGChunk.document_id.in_(request.document_ids), RAGChunk.space_id != source.id
        )
    ):
        raise CommandRejected("FORBIDDEN")
    count = int(
        await db.scalar(select(func.count(RAGDocument.id)).where(RAGDocument.space_id == target.id))
        or 0
    )
    if count + len(request.document_ids) > settings.rag_spaces_max_docs_per_space:
        raise CommandRejected("CONSTRAINT_VIOLATION")
    scope = DocumentMoveSelection(
        request=request,
        documents=selected,
        target=SpaceUpdateTarget.model_validate(target),
        target_documents=count,
        max_documents=settings.rag_spaces_max_docs_per_space,
        source_digest=payload_digest(await _source_row(db, actor_id, source.id)),
        target_digest=payload_digest(await _source_row(db, actor_id, target.id)),
        result_digest=await _private_digest(
            db, request.document_ids, normalized_space_id=target.id, ignore_updated_at=True
        ),
    )
    if len(scope.model_dump_json().encode("utf-8")) > 64_000:
        raise ValueError("Movement selection too large; select fewer documents")
    return scope
