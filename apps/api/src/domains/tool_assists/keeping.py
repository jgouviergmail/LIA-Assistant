"""A file kept in a knowledge space from the Tools (ADR-372).

The person's own act: no model answers it. The bytes come through the Tools' own doors, under the
ceiling and the transfer claim every download has, and no session is open while a provider answers
(ADR-304). The space then judges them as it judges an upload (type, size, quota), and indexes them
as it indexes an upload, on the road that spend already takes.
"""

from __future__ import annotations

from io import BytesIO
from uuid import UUID

from fastapi import UploadFile
from starlette.datastructures import Headers

from src.domains.rag_spaces.processing import process_document
from src.domains.rag_spaces.service import RAGSpaceService
from src.domains.workbench.files_service import download_file
from src.domains.workbench.mail_attachments import download_attachment
from src.domains.workbench.schemas.files import DownloadQuery
from src.domains.workbench.schemas.mail import AttachmentRequest
from src.infrastructure.async_utils import safe_fire_and_forget
from src.infrastructure.database.session import get_db_context


async def _keep(user_id: UUID, space_id: UUID, data: bytes, name: str, mime_type: str) -> UUID:
    """Hand the bytes to the space, then start its indexing, as an upload does."""
    upload = UploadFile(
        file=BytesIO(data), filename=name, headers=Headers({"content-type": mime_type})
    )
    async with get_db_context() as db:
        document = await RAGSpaceService(db).upload_document(space_id, user_id, upload)
        document_id = document.id
        stored, original, content_type = (
            document.filename,
            document.original_filename,
            document.content_type,
        )
    safe_fire_and_forget(
        process_document(
            document_id=document_id,
            space_id=space_id,
            user_id=user_id,
            filename=stored,
            original_filename=original,
            content_type=content_type,
            durable_upload=True,
        ),
        name=f"rag_process_{document_id}",
    )
    return document_id


async def keep_file(user_id: UUID, space_id: UUID, file_id: str) -> UUID:
    """Keep a drive's file in a space.

    Args:
        user_id: The account.
        space_id: The space.
        file_id: The file: a Google document leaves in its first export format.

    Returns:
        The document made.
    """
    file = await download_file(user_id, DownloadQuery(id=file_id))
    return await _keep(user_id, space_id, file.data, file.filename, file.mime_type)


async def keep_attachment(user_id: UUID, space_id: UUID, request: AttachmentRequest) -> UUID:
    """Keep a message's attachment in a space.

    Args:
        user_id: The account.
        space_id: The space.
        request: The attachment.

    Returns:
        The document made.
    """
    content = await download_attachment(user_id, request)
    name = content.filename or request.filename or ""
    return await _keep(user_id, space_id, content.data, name, content.mime_type)
