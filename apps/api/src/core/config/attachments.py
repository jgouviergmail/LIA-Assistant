"""
Attachments configuration module.

Contains settings for:
- Attachments feature toggle (enabled/disabled)
- Storage path and file size limits
- Allowed MIME types (images, documents)
- TTL for orphan file cleanup
- PDF text extraction limits

Phase: evolution F4 — File Attachments & Vision Analysis
Created: 2026-03-09
Reference: docs/technical/ATTACHMENTS_INTEGRATION.md
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    ATTACHMENTS_ALLOWED_DOC_TYPES_DEFAULT,
    ATTACHMENTS_ALLOWED_IMAGE_TYPES_DEFAULT,
    ATTACHMENTS_MAX_DOC_SIZE_MB_DEFAULT,
    ATTACHMENTS_MAX_IMAGE_SIZE_MB_DEFAULT,
    ATTACHMENTS_MAX_PDF_TEXT_CHARS_DEFAULT,
    ATTACHMENTS_MAX_PER_MESSAGE_DEFAULT,
    ATTACHMENTS_STORAGE_PATH_DEFAULT,
    ATTACHMENTS_TTL_HOURS_DEFAULT,
)


class AttachmentsSettings(BaseSettings):
    """Attachments settings for file uploads in chat (images, PDF)."""

    # ========================================================================
    # Feature Toggle
    # ========================================================================

    attachments_enabled: bool = Field(
        default=False,
        description=(
            "Enable file attachment support in chat. When true, users can "
            "upload images and PDF documents for vision LLM analysis."
        ),
    )

    # ========================================================================
    # Storage Configuration
    # ========================================================================

    attachments_storage_path: str = Field(
        default=ATTACHMENTS_STORAGE_PATH_DEFAULT,
        description="Base storage path for uploaded files on disk.",
    )

    attachments_max_image_size_mb: int = Field(
        default=ATTACHMENTS_MAX_IMAGE_SIZE_MB_DEFAULT,
        ge=1,
        le=50,
        description="Maximum image file size in MB.",
    )

    attachments_max_doc_size_mb: int = Field(
        default=ATTACHMENTS_MAX_DOC_SIZE_MB_DEFAULT,
        ge=1,
        le=100,
        description="Maximum document file size in MB.",
    )

    attachments_max_per_message: int = Field(
        default=ATTACHMENTS_MAX_PER_MESSAGE_DEFAULT,
        ge=1,
        le=10,
        description="Maximum number of attachments per chat message.",
    )

    # ========================================================================
    # MIME Types
    # ========================================================================

    attachments_allowed_image_types: str = Field(
        default=ATTACHMENTS_ALLOWED_IMAGE_TYPES_DEFAULT,
        description="Comma-separated list of allowed image MIME types.",
    )

    attachments_allowed_doc_types: str = Field(
        default=ATTACHMENTS_ALLOWED_DOC_TYPES_DEFAULT,
        description="Comma-separated list of allowed document MIME types.",
    )

    # ========================================================================
    # Lifecycle & Cleanup
    # ========================================================================

    attachments_ttl_hours: int = Field(
        default=ATTACHMENTS_TTL_HOURS_DEFAULT,
        ge=1,
        le=168,
        description="TTL safety net for orphan files in hours (cleanup scheduler).",
    )

    # ========================================================================
    # PDF Processing
    # ========================================================================

    attachments_max_pdf_text_chars: int = Field(
        default=ATTACHMENTS_MAX_PDF_TEXT_CHARS_DEFAULT,
        ge=1000,
        le=200000,
        description="Maximum characters of extracted PDF text sent to LLM.",
    )
