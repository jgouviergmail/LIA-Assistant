"""The approved selection is fenced, reopened and packed from immutable local copies."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.stored_file_response import StoredFileResponse
from src.domains.agents.application.document_archive_schemas import (
    DocumentArchivePatch,
    canonical_document_archive,
)
from src.domains.agents.application.document_archive_spec import DOCUMENT_ARCHIVE_OPERATION
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.stored_download_service import (
    Check,
    StoredDownload,
    serve_stored_download_command,
)
from src.domains.rag_spaces.document_archives import open_owned_document_archive
from src.domains.rag_spaces.models import RAGDocument
from src.domains.rag_spaces.service import RAGSpaceService


async def serve_document_archive_command(
    db: AsyncSession, actor_id: UUID, command_id: UUID, origin: ApplicationOrigin | None
) -> StoredFileResponse:
    async def prepare(draft: ApplicationActionDraftContent, check: Check) -> StoredDownload:
        if not canonical_document_archive(draft):
            raise ValueError("Archive transfer requires its exact approved selection")
        selected = DocumentArchivePatch.model_validate(draft.intent).archive_to_download
        await RAGSpaceService(db).get_space(selected.space_id, actor_id, for_update=True)
        await db.execute(
            select(RAGDocument.id)
            .where(
                RAGDocument.id.in_(document.document_id for document in selected.documents),
                RAGDocument.space_id == selected.space_id,
                RAGDocument.user_id == actor_id,
            )
            .order_by(RAGDocument.id)
            .with_for_update()
        )
        await check()
        reader = await open_owned_document_archive(db, actor_id, selected)
        return StoredDownload(
            reader,
            f"{selected.space_name}.zip",
            "application/zip",
            {
                "space_id": str(selected.space_id),
                "document_count": len(selected.documents),
                "missing_count": sum(not document.present for document in selected.documents),
            },
        )

    return await serve_stored_download_command(
        db,
        actor_id,
        command_id,
        origin,
        operation=DOCUMENT_ARCHIVE_OPERATION,
        prepare=prepare,
    )
