"""
Pydantic v2 schemas for the attachments domain.

Phase: evolution F4 — File Attachments & Vision Analysis
Created: 2026-03-09
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


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
