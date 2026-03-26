"""
Attachments API router.

Endpoints:
- POST /upload — Upload a file attachment (multipart)
- GET /{attachment_id} — Download/serve a file (ownership check)
- DELETE /{attachment_id} — Delete a file (ownership check)

Auth: Session-based (BFF pattern) via get_current_active_session.
Feature flag: ATTACHMENTS_ENABLED (routes registered conditionally).

Phase: evolution F4 — File Attachments & Vision Analysis
Created: 2026-03-09
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.attachments.schemas import AttachmentUploadResponse
from src.domains.attachments.service import AttachmentService
from src.domains.auth.models import User

router = APIRouter(prefix="/attachments", tags=["Attachments"])


@router.post(
    "/upload",
    response_model=AttachmentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a file attachment (image or PDF)",
)
async def upload_attachment(
    file: UploadFile,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> AttachmentUploadResponse:
    """
    Upload a file attachment for use in chat messages.

    Accepts images (JPEG, PNG, GIF, WebP, HEIC) and documents (PDF).
    Files are validated by magic bytes, not extension.
    HEIC images are automatically converted to JPEG.
    PDF text is extracted for LLM analysis.
    """
    service = AttachmentService(db)
    attachment = await service.upload(user_id=user.id, file=file)

    return AttachmentUploadResponse.model_validate(attachment)


@router.get(
    "/{attachment_id}",
    summary="Download/serve an attachment file",
    responses={404: {"description": "Attachment not found or file missing from disk"}},
)
async def get_attachment(
    attachment_id: uuid.UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """
    Serve a file attachment with ownership verification.

    Returns the file with appropriate Content-Type header.
    Only the file owner can access their attachments.
    """
    from pathlib import Path

    settings = get_settings()
    service = AttachmentService(db)
    attachment = await service.get_for_user(
        attachment_id=attachment_id,
        user_id=user.id,
    )

    file_path = Path(settings.attachments_storage_path) / attachment.file_path

    # Defensive check: file may have been cleaned from disk but DB record persists
    if not file_path.is_file():
        from src.domains.attachments.service import raise_attachment_not_found

        raise_attachment_not_found(attachment_id)

    # Use "inline" disposition for images so browsers recognise the resource
    # as a displayable image — this enables the native long-press "Save Image"
    # context menu on mobile (iOS Safari, Android Chrome).
    # Non-image attachments keep "attachment" to trigger a download prompt.
    is_image = attachment.mime_type.startswith("image/")

    return FileResponse(
        path=str(file_path),
        media_type=attachment.mime_type,
        filename=attachment.original_filename,
        content_disposition_type="inline" if is_image else "attachment",
    )


@router.delete(
    "/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an attachment",
)
async def delete_attachment(
    attachment_id: uuid.UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a file attachment (DB record + file on disk).

    Only the file owner can delete their attachments.
    """
    service = AttachmentService(db)
    await service.delete_for_user_single(
        attachment_id=attachment_id,
        user_id=user.id,
    )
