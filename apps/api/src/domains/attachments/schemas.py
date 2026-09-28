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
    expires_at: datetime | None = Field(
        default=None,
        description=(
            "When the cleanup removes it (UTC) — stated, never implied. None: the "
            "person kept it, and no cleanup will (ADR-319)."
        ),
    )
    shared_by_name: str | None = Field(
        default=None,
        description="Who shared this image, for a copy a connection sent (ADR-316); None otherwise.",
    )


class GeneratedAssetKeepUsage(BaseModel):
    """What the account keeps past the deadline, against what it may (ADR-319).

    Published with every listing because it is enforced (ADR-184): the gallery
    says « 12 of 100 kept » before a click is refused.
    """

    model_config = ConfigDict(from_attributes=True)

    kept_files: int = Field(description="EXACT count of the account's kept files, every family.")
    kept_bytes: int = Field(description="EXACT bytes those kept files hold.")
    max_files: int = Field(description="Most files the account may keep (0 = keeping is off).")
    max_bytes: int = Field(description="Most bytes the account may keep (0 = keeping is off).")


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
    keep: GeneratedAssetKeepUsage = Field(
        description="What the account keeps past the deadline, and its ceilings (ADR-319).",
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


class GeneratedAssetsKeepRequest(BaseModel):
    """Keep a selection past its deadline, or give it a deadline again."""

    ids: list[uuid.UUID] = Field(min_length=1, max_length=100, description="The files.")
    kept: bool = Field(
        description="True keeps them (no cleanup); False releases them (a TTL from now).",
    )


class GeneratedAssetsKeepResponse(BaseModel):
    """What actually changed, what did not, and the account's usage after it.

    Two lists rather than a count, like the bulk delete: an upload, a file of
    someone else or one the cleanup removed must not be counted (ADR-185).
    """

    updated: list[uuid.UUID] = Field(description="Files now in the requested state.")
    skipped: list[uuid.UUID] = Field(description="Files that could not be changed.")
    keep: GeneratedAssetKeepUsage = Field(description="The account's usage after the change.")
