"""
RAG Spaces router with FastAPI endpoints.

Provides CRUD operations for spaces and documents, plus admin
endpoints for reindexation after embedding model changes.

Phase: evolution — RAG Spaces (User Knowledge Documents)
Created: 2026-03-14
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.exceptions import BaseAPIException
from src.core.session_dependencies import (
    get_current_active_session,
    get_current_superuser_session,
)
from src.domains.auth.models import User
from src.domains.rag_spaces.drive_sync import RAGDriveSyncService, sync_folder_background
from src.domains.rag_spaces.processing import process_document
from src.domains.rag_spaces.reindex import get_reindex_status as _get_reindex_status
from src.domains.rag_spaces.reindex import start_reindexation
from src.domains.rag_spaces.schemas import (
    RAGDocumentResponse,
    RAGDocumentStatusResponse,
    RAGDriveSourceCreate,
    RAGDriveSourceResponse,
    RAGDriveSyncStatusResponse,
    RAGReindexResponse,
    RAGReindexStatusResponse,
    RAGSpaceCreate,
    RAGSpaceDetailResponse,
    RAGSpaceListResponse,
    RAGSpaceResponse,
    RAGSpaceToggleResponse,
    RAGSpaceUpdate,
    SystemSpaceListResponse,
    SystemSpaceReindexResponse,
    SystemSpaceResponse,
    SystemSpaceStalenessResponse,
)
from src.domains.rag_spaces.service import RAGSpaceService
from src.infrastructure.async_utils import safe_fire_and_forget

router = APIRouter(
    prefix="/rag-spaces",
    tags=["RAG Spaces"],
)


# ============================================================================
# Admin: Reindexation (MUST be defined BEFORE /{space_id} routes to avoid
# FastAPI matching "admin" as a UUID path parameter)
# ============================================================================


@router.post(
    "/admin/reindex",
    response_model=RAGReindexResponse,
    summary="Trigger full reindexation (admin)",
)
async def trigger_reindex(
    user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> RAGReindexResponse:
    """
    Trigger reindexation of all RAG documents across all users.

    Called after changing the embedding model in admin settings.
    Runs in background — poll the status endpoint for progress.
    """
    result = await start_reindexation(db)
    return RAGReindexResponse(**result)


@router.get(
    "/admin/reindex/status",
    response_model=RAGReindexStatusResponse,
    summary="Get reindexation status (admin)",
)
async def get_reindex_status(
    user: User = Depends(get_current_superuser_session),
) -> RAGReindexStatusResponse:
    """Check the status of an ongoing reindexation."""
    result = await _get_reindex_status()
    return RAGReindexStatusResponse(**result)


# ============================================================================
# Admin: System Spaces (MUST be defined BEFORE /{space_id} routes)
# ============================================================================


@router.get(
    "/admin/system-spaces",
    response_model=SystemSpaceListResponse,
    summary="List system knowledge spaces (admin)",
)
async def list_system_spaces(
    user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> SystemSpaceListResponse:
    """List all system spaces with stats (document count, chunk count, staleness)."""
    service = RAGSpaceService(db)
    spaces = await service.get_system_spaces()
    return SystemSpaceListResponse(
        spaces=[SystemSpaceResponse(**s) for s in spaces],
        total=len(spaces),
    )


@router.post(
    "/admin/system-spaces/{space_name}/reindex",
    response_model=SystemSpaceReindexResponse,
    summary="Reindex a system space (admin)",
)
async def reindex_system_space(
    space_name: str,
    user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> SystemSpaceReindexResponse:
    """Trigger reindexation of a system space (FAQ knowledge base)."""
    from src.domains.rag_spaces.system_indexer import SystemSpaceIndexer

    indexer = SystemSpaceIndexer(db)
    result = await indexer.index_faq_space()

    if result["status"] == "error":
        raise BaseAPIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "Indexation failed"),
            log_event="system_space_reindex_failed",
            space_name=space_name,
        )

    return SystemSpaceReindexResponse(
        message=(
            f"System space '{space_name}' reindexed successfully"
            if result["status"] == "success"
            else f"System space '{space_name}' is already up to date"
        ),
        space_name=space_name,
        chunks_created=result["chunks_created"],
        content_hash=result["content_hash"],
    )


@router.get(
    "/admin/system-spaces/{space_name}/staleness",
    response_model=SystemSpaceStalenessResponse,
    summary="Check system space staleness (admin)",
)
async def check_system_space_staleness(
    space_name: str,
    user: User = Depends(get_current_superuser_session),
    db: AsyncSession = Depends(get_db),
) -> SystemSpaceStalenessResponse:
    """Check if a system space needs reindexation (content hash comparison)."""
    from src.domains.rag_spaces.system_indexer import SystemSpaceIndexer

    indexer = SystemSpaceIndexer(db)
    result = await indexer.check_staleness(space_name)
    return SystemSpaceStalenessResponse(
        space_name=space_name,
        **result,
    )


# ============================================================================
# Space CRUD
# ============================================================================


@router.get(
    "",
    response_model=RAGSpaceListResponse,
    summary="List user's RAG spaces",
)
async def list_spaces(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> RAGSpaceListResponse:
    """List all RAG spaces for the current user with computed stats."""
    service = RAGSpaceService(db)
    spaces = await service.list_spaces(user.id)
    return RAGSpaceListResponse(
        spaces=[RAGSpaceResponse(**s) for s in spaces],
        total=len(spaces),
    )


@router.post(
    "",
    response_model=RAGSpaceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a RAG space",
)
async def create_space(
    data: RAGSpaceCreate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> RAGSpaceResponse:
    """Create a new RAG space for the current user."""
    service = RAGSpaceService(db)
    space = await service.create_space(
        user_id=user.id,
        name=data.name,
        description=data.description,
    )
    # Return with default stats (new space has no documents)
    return RAGSpaceResponse(
        **space.dict(),
        document_count=0,
        total_size=0,
        ready_document_count=0,
    )


@router.get(
    "/{space_id}",
    response_model=RAGSpaceDetailResponse,
    summary="Get space detail with documents",
)
async def get_space_detail(
    space_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> RAGSpaceDetailResponse:
    """Get detailed view of a space including documents and Drive sources."""
    service = RAGSpaceService(db)
    detail = await service.get_space_detail(space_id, user.id)
    nested_keys = {"documents", "drive_sources"}
    return RAGSpaceDetailResponse(
        **{k: v for k, v in detail.items() if k not in nested_keys},
        documents=[RAGDocumentResponse(**d) for d in detail["documents"]],
        drive_sources=[RAGDriveSourceResponse(**s) for s in detail.get("drive_sources", [])],
    )


@router.patch(
    "/{space_id}",
    response_model=RAGSpaceResponse,
    summary="Update a RAG space",
)
async def update_space(
    space_id: UUID,
    data: RAGSpaceUpdate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> RAGSpaceResponse:
    """Update space name and/or description."""
    service = RAGSpaceService(db)
    result = await service.update_space_with_stats(
        space_id=space_id,
        user_id=user.id,
        name=data.name,
        description=data.description,
    )
    return RAGSpaceResponse(**result)


@router.delete(
    "/{space_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a RAG space",
)
async def delete_space(
    space_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a space with all its documents, chunks, and files."""
    service = RAGSpaceService(db)
    await service.delete_space(space_id, user.id)


@router.patch(
    "/{space_id}/toggle",
    response_model=RAGSpaceToggleResponse,
    summary="Toggle space activation",
)
async def toggle_space(
    space_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> RAGSpaceToggleResponse:
    """Activate or deactivate a space for RAG retrieval."""
    service = RAGSpaceService(db)
    space = await service.toggle_space(space_id, user.id)
    return RAGSpaceToggleResponse(id=space.id, is_active=space.is_active)


# ============================================================================
# Document Management
# ============================================================================


@router.post(
    "/{space_id}/documents",
    response_model=RAGDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document",
)
async def upload_document(
    space_id: UUID,
    file: UploadFile,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> RAGDocumentResponse:
    """
    Upload a document to a space.

    Accepted formats: TXT, MD, PDF, DOCX, PPTX, XLSX, CSV, RTF,
    HTML, ODT, ODS, ODP, EPUB, JSON, XML.
    The document is processed asynchronously (chunking + embedding).
    Poll the status endpoint to check processing progress.
    """
    service = RAGSpaceService(db)
    document = await service.upload_document(space_id, user.id, file)

    # Launch background processing
    safe_fire_and_forget(
        process_document(
            document_id=document.id,
            space_id=space_id,
            user_id=user.id,
            filename=document.filename,
            original_filename=document.original_filename,
            content_type=document.content_type,
        ),
        name=f"rag_process_{document.id}",
    )

    return RAGDocumentResponse.model_validate(document)


@router.delete(
    "/{space_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
)
async def delete_document(
    space_id: UUID,
    document_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a document with its chunks and physical file."""
    service = RAGSpaceService(db)
    await service.delete_document(space_id, document_id, user.id)


@router.get(
    "/{space_id}/documents/{document_id}/status",
    response_model=RAGDocumentStatusResponse,
    summary="Get document processing status",
)
async def get_document_status(
    space_id: UUID,
    document_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> RAGDocumentStatusResponse:
    """Check the processing status of an uploaded document."""
    service = RAGSpaceService(db)
    document = await service.get_document_status(space_id, document_id, user.id)
    return RAGDocumentStatusResponse(
        id=document.id,
        status=document.status,
        error_message=document.error_message,
        chunk_count=document.chunk_count,
    )


# ============================================================================
# Drive Sources
# ============================================================================


@router.get(
    "/{space_id}/drive-browse",
    response_model=dict,
    summary="Browse Google Drive folder contents",
)
async def browse_drive_contents(
    space_id: UUID,
    folder_id: str = Query(default="root"),
    page_token: str | None = Query(default=None),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Browse Drive folder contents (folders + files) for the folder picker."""
    service = RAGDriveSyncService(db)
    return await service.browse_drive_contents(user.id, folder_id, page_token)


@router.post(
    "/{space_id}/drive-sources",
    response_model=RAGDriveSourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Link a Drive folder",
)
async def link_drive_folder(
    space_id: UUID,
    data: RAGDriveSourceCreate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> RAGDriveSourceResponse:
    """Link a Google Drive folder to a RAG space for sync."""
    service = RAGDriveSyncService(db)
    source = await service.link_folder(space_id, user.id, data.folder_id, data.folder_name)
    return RAGDriveSourceResponse.model_validate(source)


@router.get(
    "/{space_id}/drive-sources",
    response_model=list[RAGDriveSourceResponse],
    summary="List linked Drive folders",
)
async def list_drive_sources(
    space_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> list[RAGDriveSourceResponse]:
    """List all Google Drive folders linked to a space."""
    service = RAGSpaceService(db)
    sources = await service.list_drive_sources(space_id, user.id)
    return [RAGDriveSourceResponse.model_validate(s) for s in sources]


@router.delete(
    "/{space_id}/drive-sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unlink a Drive folder",
)
async def unlink_drive_folder(
    space_id: UUID,
    source_id: UUID,
    delete_documents: bool = Query(default=False),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Unlink a Google Drive folder from a space."""
    service = RAGDriveSyncService(db)
    await service.unlink_folder(space_id, source_id, user.id, delete_documents)


@router.post(
    "/{space_id}/drive-sources/{source_id}/sync",
    response_model=RAGDriveSyncStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger Drive folder sync",
)
async def sync_drive_folder(
    space_id: UUID,
    source_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> RAGDriveSyncStatusResponse:
    """Trigger manual sync of a Drive folder. Returns 202 Accepted."""
    service = RAGDriveSyncService(db)

    # Verify ownership
    await service.get_sync_status(space_id, source_id, user.id)

    # Atomic lock
    acquired = await service.try_acquire_sync_lock(source_id)
    if not acquired:
        raise BaseAPIException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sync already in progress",
            log_event="rag_drive_sync_already_running",
            source_id=str(source_id),
        )

    # Launch background sync
    safe_fire_and_forget(
        sync_folder_background(space_id, source_id, user.id),
        name=f"drive_sync_{source_id}",
    )

    # Refetch after lock to return current status
    source = await service.get_sync_status(space_id, source_id, user.id)
    return RAGDriveSyncStatusResponse(
        sync_status=source.sync_status,
        last_sync_at=source.last_sync_at,
        file_count=source.file_count,
        synced_file_count=source.synced_file_count,
        error_message=source.error_message,
    )


@router.get(
    "/{space_id}/drive-sources/{source_id}/sync-status",
    response_model=RAGDriveSyncStatusResponse,
    summary="Get sync status",
)
async def get_drive_sync_status(
    space_id: UUID,
    source_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> RAGDriveSyncStatusResponse:
    """Get the current sync status of a Drive folder source."""
    service = RAGDriveSyncService(db)
    source = await service.get_sync_status(space_id, source_id, user.id)
    return RAGDriveSyncStatusResponse(
        sync_status=source.sync_status,
        last_sync_at=source.last_sync_at,
        file_count=source.file_count,
        synced_file_count=source.synced_file_count,
        error_message=source.error_message,
    )
