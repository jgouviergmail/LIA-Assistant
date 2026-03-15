"""
Pydantic schemas for RAG Spaces API.

Defines request/response models for spaces, documents, and related operations.

Phase: evolution — RAG Spaces (User Knowledge Documents)
Created: 2026-03-14
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ============================================================================
# Space Schemas
# ============================================================================


class RAGSpaceCreate(BaseModel):
    """Create a new RAG space."""

    name: str = Field(
        min_length=2,
        max_length=200,
        description="Space name (unique per user)",
    )
    description: str | None = Field(
        None,
        max_length=2000,
        description="Optional space description",
    )


class RAGSpaceUpdate(BaseModel):
    """Update an existing RAG space (partial update)."""

    name: str | None = Field(
        None,
        min_length=2,
        max_length=200,
        description="Updated space name",
    )
    description: str | None = Field(
        None,
        max_length=2000,
        description="Updated space description",
    )


class RAGSpaceResponse(BaseModel):
    """Space data for API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    is_active: bool
    document_count: int = Field(default=0, description="Total number of documents")
    total_size: int = Field(default=0, description="Total file size in bytes")
    ready_document_count: int = Field(default=0, description="Number of documents ready for search")
    created_at: datetime
    updated_at: datetime


class RAGSpaceDetailResponse(RAGSpaceResponse):
    """Detailed space response with documents list."""

    documents: list["RAGDocumentResponse"] = Field(default_factory=list)


class RAGSpaceListResponse(BaseModel):
    """Paginated list of spaces."""

    spaces: list[RAGSpaceResponse]
    total: int


# ============================================================================
# Document Schemas
# ============================================================================


class RAGDocumentResponse(BaseModel):
    """Document data for API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_filename: str
    file_size: int
    content_type: str
    status: str
    error_message: str | None
    chunk_count: int
    embedding_model: str | None
    embedding_tokens: int = 0
    embedding_cost_eur: float = 0.0
    created_at: datetime


class RAGDocumentStatusResponse(BaseModel):
    """Document processing status response."""

    id: UUID
    status: str
    error_message: str | None
    chunk_count: int


# ============================================================================
# Toggle Schema
# ============================================================================


class RAGSpaceToggleResponse(BaseModel):
    """Response after toggling space activation."""

    id: UUID
    is_active: bool


# ============================================================================
# Reindex Schemas
# ============================================================================


class RAGReindexResponse(BaseModel):
    """Response after triggering reindexation."""

    message: str
    total_documents: int
    model_from: str | None
    model_to: str


class RAGReindexStatusResponse(BaseModel):
    """Status of an ongoing reindexation."""

    in_progress: bool
    started_at: str | None = None
    model_from: str | None = None
    model_to: str | None = None
    total_documents: int = 0
    processed_documents: int = 0
    failed_documents: int = 0
