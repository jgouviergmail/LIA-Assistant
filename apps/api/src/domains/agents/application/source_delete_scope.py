"""Whole-source intent uses the existing exact document/chunk/file deletion witnesses."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import RAG_SPACES_BULK_MAX
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.document_delete_schemas import DocumentDeleteInput
from src.domains.agents.application.document_delete_scope import document_deletion_selection
from src.domains.agents.application.source_delete_schemas import (
    SourceDeleteInput,
    SourceDeleteSelection,
)
from src.domains.agents.application.source_unlink_schemas import SourceUnlinkInput
from src.domains.agents.application.source_unlink_scope import source_unlink_selection
from src.domains.rag_spaces.models import RAGDocument


async def source_deletion_selection(
    db: AsyncSession, actor_id: UUID, request: SourceDeleteInput, *, lock: bool = False
) -> SourceDeleteSelection:
    source = await source_unlink_selection(
        db, actor_id, SourceUnlinkInput.model_validate(request.model_dump()), lock=lock
    )
    reference = (
        RAGDocument.drive_source_id if request.kind == "drive" else RAGDocument.mail_source_id
    )
    ids = tuple(
        (
            await db.scalars(
                select(RAGDocument.id)
                .where(
                    reference == request.source_id,
                    RAGDocument.user_id == actor_id,
                    RAGDocument.space_id == request.space_id,
                )
                .order_by(RAGDocument.id)
            )
        ).all()
    )
    if len(ids) != source.documents:
        raise CommandRejected("STALE_STATE")
    batches = []
    for offset in range(0, len(ids), RAG_SPACES_BULK_MAX):
        batches.append(
            await document_deletion_selection(
                db,
                actor_id,
                DocumentDeleteInput(
                    space_id=request.space_id,
                    document_ids=ids[offset : offset + RAG_SPACES_BULK_MAX],
                ),
            )
        )
    selected = SourceDeleteSelection(source=source, batches=tuple(batches))
    if len(selected.model_dump_json().encode("utf-8")) > 64_000:
        raise CommandRejected("CONSTRAINT_VIOLATION")
    return selected
