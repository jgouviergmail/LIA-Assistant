"""
Attachment SQLAlchemy model.

Stores metadata for uploaded files (images, PDF documents).
Files are stored on disk; this model tracks ownership, MIME type,
storage path, and lifecycle status.

Phase: evolution F4 — File Attachments & Vision Analysis
Created: 2026-03-09
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel

# --- Domain constants (str, not Enum — avoids _CHECKPOINT_ALLOWED_MODULES registration) ---


class AttachmentStatus:
    """Lifecycle status values for attachments."""

    UPLOADED = "uploaded"
    READY = "ready"
    EXPIRED = "expired"


class AttachmentContentType:
    """Content category values for attachments."""

    IMAGE = "image"
    DOCUMENT = "document"


class Attachment(BaseModel):
    """
    Uploaded file attachment linked to a user.

    Lifecycle:
        uploaded → ready (after validation + optional text extraction)
        ready → expired (TTL safety net or conversation reset)

    Security:
        - Files stored as UUID-based filenames (anti-traversal)
        - Physical directory segmentation by user_id
        - All access paths verify user_id ownership
    """

    __tablename__ = "attachments"

    # Foreign key to user (cascade delete when user is removed)
    # Note: standalone index omitted — covered by composite ix_attachments_user_id_created_at
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Original filename (for display only, never used in file paths)
    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # UUID-based stored filename (anti-path-traversal)
    stored_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # MIME type (validated by magic bytes, not extension)
    mime_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # File size in bytes
    file_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Relative path from ATTACHMENTS_STORAGE_PATH
    file_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    # Content category: "image" or "document"
    content_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    # Extracted text from PDF (None for images)
    extracted_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )

    # Lifecycle status: AttachmentStatus.UPLOADED → READY → EXPIRED
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=AttachmentStatus.UPLOADED,
        index=True,
    )

    # Expiration timestamp (TTL safety net for orphan cleanup)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # Composite index for user queries (ownership + chronological order)
    __table_args__ = (Index("ix_attachments_user_id_created_at", "user_id", "created_at"),)
