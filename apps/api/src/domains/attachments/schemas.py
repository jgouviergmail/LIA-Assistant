"""
Pydantic v2 schemas for the attachments domain.

Phase: evolution F4 — File Attachments & Vision Analysis
Created: 2026-03-09
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AttachmentUploadResponse(BaseModel):
    """Response schema for a successful file upload."""

    id: uuid.UUID = Field(description="Unique attachment identifier.")
    original_filename: str = Field(description="Original filename as uploaded by user.")
    mime_type: str = Field(description="Validated MIME type (by magic bytes).")
    file_size: int = Field(description="File size in bytes.")
    content_type: str = Field(description="Content category: 'image' or 'document'.")
    created_at: datetime = Field(description="Upload timestamp (UTC).")

    model_config = {"from_attributes": True}


class AttachmentMeta(BaseModel):
    """Lightweight metadata stored in ConversationMessage.message_metadata JSONB."""

    id: str = Field(description="Attachment UUID as string.")
    filename: str = Field(description="Original filename for display.")
    mime_type: str = Field(description="MIME type.")
    size: int = Field(description="File size in bytes.")
    content_type: str = Field(description="Content category: 'image' or 'document'.")


class GeneratedAssetSummary(BaseModel):
    """One file LIA produced, as the gallery shows it (ADR-279)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Attachment id; also the download path segment.")
    title: str | None = Field(
        default=None,
        description="What the file is called for a person; None falls back to the filename.",
    )
    original_filename: str = Field(description="Download filename.")
    mime_type: str = Field(description="MIME type.")
    file_size: int = Field(description="Size in bytes.")
    origin: str = Field(description="Which producer filed it.")
    conversation_id: uuid.UUID | None = Field(
        default=None,
        description="Where it was produced; None when the conversation is gone or there was none.",
    )
    created_at: datetime = Field(description="When it was produced (UTC).")
    expires_at: datetime = Field(
        description="When the cleanup removes it (UTC) — stated, never implied.",
    )


class GeneratedAssetListResponse(BaseModel):
    """One page of one gallery, its exact total, and the bounds it obeys."""

    items: list[GeneratedAssetSummary]
    total: int = Field(description="EXACT count over the whole filtered set (ADR-185).")
    total_bytes: int = Field(description="EXACT sum of the sizes behind that count.")
    limit: int = Field(description="Page size applied.")
    offset: int = Field(description="Page start applied.")
    max_limit: int = Field(
        description="Largest page this API serves — published because it is enforced (ADR-184).",
    )


class GeneratedAssetsDeleteRequest(BaseModel):
    """A selection to remove."""

    ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class GeneratedAssetsDeleteResponse(BaseModel):
    """What actually went, and what did not.

    Two lists rather than a count: a file that expired between the listing and
    the click, or one the caller does not own, must not be counted as deleted.
    """

    deleted: list[uuid.UUID]
    skipped: list[uuid.UUID]
