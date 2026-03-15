"""
RAG Spaces router with FastAPI endpoints.

Provides CRUD operations for spaces and documents, plus admin
endpoints for reindexation after embedding model changes.

Phase: evolution — RAG Spaces (User Knowledge Documents)
Created: 2026-03-14
"""

from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.session_dependencies import (
    get_current_active_session,
    get_current_superuser_session,
)
from src.domains.auth.models import User
from src.domains.rag_spaces.processing import process_document
from src.domains.rag_spaces.reindex import get_reindex_status as _get_reindex_status
from src.domains.rag_spaces.reindex import start_reindexation
from src.domains.rag_spaces.schemas import (
    RAGDocumentResponse,
    RAGDocumentStatusResponse,
    RAGReindexResponse,
    RAGReindexStatusResponse,
    RAGSpaceCreate,
    RAGSpaceDetailResponse,
    RAGSpaceListResponse,
    RAGSpaceResponse,
    RAGSpaceToggleResponse,
    RAGSpaceUpdate,
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
    """Get detailed view of a space including documents list."""
    service = RAGSpaceService(db)
    detail = await service.get_space_detail(space_id, user.id)
    return RAGSpaceDetailResponse(
        **{k: v for k, v in detail.items() if k != "documents"},
        documents=[RAGDocumentResponse(**d) for d in detail["documents"]],
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

    Accepted formats: TXT, MD, PDF, DOCX.
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
