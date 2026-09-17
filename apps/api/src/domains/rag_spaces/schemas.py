"""
Pydantic schemas for RAG Spaces API.

Defines request/response models for spaces, documents, and related operations.

Phase: evolution — RAG Spaces (User Knowledge Documents)
Created: 2026-03-14
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.core.constants import RAG_SPACES_BULK_MAX

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
    kind: str | None = Field(
        default=None,
        description=(
            "Role of a space another domain manages by identity ('meetings', "
            "'bookmarks'); None for a space the person created. A managed space "
            "is drawn as such and cannot be deleted by hand."
        ),
    )
    document_count: int = Field(default=0, description="Total number of documents")
    total_size: int = Field(default=0, description="Total file size in bytes")
    ready_document_count: int = Field(default=0, description="Number of documents ready for search")
    created_at: datetime
    updated_at: datetime


class RAGSpaceDetailResponse(RAGSpaceResponse):
    """Detailed space response with documents and Drive sources."""

    documents: list[RAGDocumentResponse] = Field(default_factory=list)
    drive_sources: list[RAGDriveSourceResponse] = Field(default_factory=list)
    mail_sources: list[RAGMailSourceResponse] = Field(
        default_factory=list, description="Gmail labels linked to the space (ADR-262)."
    )


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
    error_code: str | None = Field(
        None, description="Why the indexing failed (RAGDocumentErrorCode), translated at display."
    )
    chunk_count: int
    embedding_model: str | None
    embedding_tokens: int = 0
    embedding_cost_eur: float = 0.0
    source_type: str = "upload"
    drive_file_id: str | None = None
    mail_thread_id: str | None = Field(
        default=None, description="Gmail thread this document renders (ADR-262)."
    )
    created_at: datetime


class RAGDocumentStatusResponse(BaseModel):
    """Document processing status response."""

    id: UUID
    status: str
    error_message: str | None
    error_code: str | None = Field(
        None, description="Why the indexing failed (RAGDocumentErrorCode), translated at display."
    )
    chunk_count: int


# ============================================================================
# Document batch operations (ADR-259)
# ============================================================================


class RAGDocumentIdsRequest(BaseModel):
    """A set of documents of one space to act on together."""

    ids: list[UUID] = Field(
        ...,
        min_length=1,
        max_length=RAG_SPACES_BULK_MAX,
        description="Documents of the space; duplicates are ignored.",
    )


class RAGDocumentMoveRequest(RAGDocumentIdsRequest):
    """Move documents to another space of the same user."""

    target_space_id: UUID = Field(..., description="The space to move the documents into.")


class RAGBatchSkipped(BaseModel):
    """One id a batch left untouched, with the stable reason the UI localizes."""

    id: UUID = Field(..., description="The document that was skipped.")
    code: str = Field(..., description="Why (same_space, document_busy, delete_failed…).")


class RAGDocumentBatchResponse(BaseModel):
    """What a batch did: the ids it handled and the ones it skipped."""

    done: list[UUID] = Field(default_factory=list, description="Ids handled in order.")
    skipped: list[RAGBatchSkipped] = Field(default_factory=list, description="Ids left untouched.")


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


# ============================================================================
# Drive Source Schemas
# ============================================================================


class RAGDriveSourceCreate(BaseModel):
    """Request body to link a Google Drive folder to a RAG space."""

    # A Drive id is an opaque token; the shape keeps a path fragment out of
    # the ``/files/{id}`` request the link builds from it.
    folder_id: str = Field(max_length=255, pattern=r"^[A-Za-z0-9_-]+$")
    folder_name: str = Field(max_length=500)


class RAGDriveSourceResponse(BaseModel):
    """Drive source data for API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    folder_id: str
    folder_name: str
    sync_status: str
    last_sync_at: datetime | None
    file_count: int
    synced_file_count: int
    error_message: str | None
    created_at: datetime


class RAGDriveSyncStatusResponse(BaseModel):
    """Sync status for a Drive source."""

    sync_status: str
    last_sync_at: datetime | None
    file_count: int
    synced_file_count: int
    error_message: str | None


class RAGDrivePreflightResponse(BaseModel):
    """What a synchronisation would index, counted by the code that indexes.

    Every figure is exact for the walk that produced it; ``truncated`` says
    a bound cut the walk, which makes every count a floor. The threshold and
    the bounds are published because they are enforced (ADR-184).
    """

    model_config = ConfigDict(from_attributes=True)

    total_files: int = Field(description="Files found in the tree (folders excluded).")
    unsupported: int = Field(description="Files whose type the pipeline cannot read.")
    unchanged: int = Field(description="Files already indexed and current.")
    modified: int = Field(description="Files indexed but changed on Drive since.")
    new: int = Field(description="Supported files never indexed.")
    over_capacity: int = Field(description="New files the space's document cap leaves out.")
    to_index: int = Field(
        description="Files the synchronisation would write (modified + new within capacity)."
    )
    folders: int = Field(description="Folders walked, the root included.")
    unreadable_folders: int = Field(description="Sub-folders the account could not list.")
    truncated: bool = Field(description="A bound stopped the walk: the counts are floors.")
    threshold: int = Field(description="Files past which a confirmation is asked.")
    max_files: int = Field(description="The walk's file bound.")
    max_folders: int = Field(description="The walk's folder bound.")
    requires_confirmation: bool = Field(description="``to_index`` exceeds the threshold.")


# ============================================================================
# Mail source schemas (ADR-262)
# ============================================================================


class RAGMailSourceCreate(BaseModel):
    """Request body to link a Gmail label to a RAG space."""

    label_id: str = Field(max_length=255, description="Gmail label id (e.g. Label_123).")
    label_name: str = Field(max_length=500, description="Display name of the label.")


class RAGMailSourceResponse(BaseModel):
    """Mail source data for API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    label_id: str = Field(description="Gmail label id.")
    label_name: str = Field(description="Display name of the label.")
    sync_status: str = Field(description="idle | syncing | completed | error.")
    last_sync_at: datetime | None = Field(description="Last successful sync.")
    thread_count: int = Field(description="Threads under the label at the last full sync.")
    synced_thread_count: int = Field(description="Threads whose document is indexed.")
    error_message: str | None = Field(description="Last error, when sync_status is error.")
    created_at: datetime


class RAGMailSyncStatusResponse(BaseModel):
    """Sync status for a mail source."""

    sync_status: str = Field(description="idle | syncing | completed | error.")
    last_sync_at: datetime | None = Field(description="Last successful sync.")
    thread_count: int = Field(description="Threads under the label at the last full sync.")
    synced_thread_count: int = Field(description="Threads whose document is indexed.")
    error_message: str | None = Field(description="Last error, when sync_status is error.")


class GmailLabelResponse(BaseModel):
    """One Gmail label the user may link (the picker's rows)."""

    id: str = Field(description="Gmail label id.")
    name: str = Field(description="Display name.")


# ============================================================================
# System Space Schemas
# ============================================================================


class SystemSpaceResponse(BaseModel):
    """System space data for admin API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    is_active: bool
    is_system: bool = Field(default=True, description="Always true for system spaces")
    content_hash: str | None = Field(default=None, description="SHA-256 hash of source content")
    document_count: int = Field(default=0, description="Total number of documents")
    chunk_count: int = Field(default=0, description="Total number of indexed chunks")
    created_at: datetime
    updated_at: datetime


class SystemSpaceListResponse(BaseModel):
    """List of system spaces for admin API."""

    spaces: list[SystemSpaceResponse]
    total: int


class SystemSpaceReindexResponse(BaseModel):
    """Response after triggering system space reindexation."""

    message: str
    space_name: str
    status: Literal["success", "skipped"] = Field(
        description=(
            "Whether the corpus was rebuilt or was already current. Machine "
            "readable on purpose: a caller cannot tell the two apart from "
            "chunks_created alone without assuming a rebuild always writes at "
            "least one chunk, and the admin UI used to report both as a success."
        )
    )
    chunks_created: int = Field(description="Number of chunks created during indexation")
    content_hash: str = Field(description="SHA-256 hash of indexed content")


class SystemSpaceStalenessResponse(BaseModel):
    """Staleness check result for a system space."""

    space_name: str
    is_stale: bool
    stored_hash: str | None = Field(description="Hash stored in database from last indexation")
    current_hash: str = Field(description="Hash computed from current source files")
