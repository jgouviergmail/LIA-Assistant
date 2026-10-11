"""One original-browser HITL continuation starts an exact owned file transfer."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.stored_file_response import StoredFileResponse
from src.domains.agents.application.document_download_schemas import (
    DocumentDownloadPatch,
    canonical_document_download,
)
from src.domains.agents.application.document_download_spec import DOCUMENT_DOWNLOAD_OPERATION
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.stored_download_service import (
    Check,
    StoredDownload,
    serve_stored_download_command,
)
from src.domains.rag_spaces.document_downloads import open_owned_document_download
from src.domains.rag_spaces.models import RAGDocument
from src.domains.rag_spaces.service import RAGSpaceService


async def serve_document_download_command(
    db: AsyncSession, actor_id: UUID, command_id: UUID, origin: ApplicationOrigin | None
) -> StoredFileResponse:
    async def prepare(draft: ApplicationActionDraftContent, check: Check) -> StoredDownload:
        if not canonical_document_download(draft):
            raise ValueError("Document transfer requires its exact approved scope")
        selected = DocumentDownloadPatch.model_validate(draft.intent).document_to_download
        await RAGSpaceService(db).get_space(selected.space_id, actor_id, for_update=True)
        await db.execute(
            select(RAGDocument.id)
            .where(
                RAGDocument.id == selected.document_id,
                RAGDocument.space_id == selected.space_id,
                RAGDocument.user_id == actor_id,
            )
            .with_for_update()
        )
        await check()
        reader = await open_owned_document_download(db, actor_id, selected)
        try:
            await reader.freeze(max_bytes=selected.file_size_bytes)
            return StoredDownload(
                reader,
                selected.original_filename,
                selected.content_type,
                {"document_id": str(selected.document_id)},
            )
        except BaseException:
            await reader.close()
            raise

    return await serve_stored_download_command(
        db,
        actor_id,
        command_id,
        origin,
        operation=DOCUMENT_DOWNLOAD_OPERATION,
        prepare=prepare,
    )
