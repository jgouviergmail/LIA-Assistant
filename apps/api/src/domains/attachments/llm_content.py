"""
LLM content builders for attachments.

Pure functions to construct:
- Vision-capable HumanMessage (multimodal content with base64 images)
- Lightweight text hints for Router/Planner awareness

These are separated from the service for Separation of Concerns:
the service handles I/O (upload, DB, disk), while this module
handles LLM message formatting (pure transformations).

Phase: evolution F4 — File Attachments & Vision Analysis
Created: 2026-03-09
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import structlog
from langchain_core.messages import HumanMessage

from src.domains.attachments.models import AttachmentContentType

logger = structlog.get_logger(__name__)

# Unique marker prefix used to delimit attachment hints in HumanMessage text.
# Must be unique enough to never appear in natural user text.
# Used by response_node to strip the hint before building multimodal message.
ATTACHMENT_HINT_MARKER = "<<ATTACHMENTS>>"

# Language-specific labels for attachment hints
_HINT_LABELS: dict[str, dict[str, str]] = {
    "fr": {"attachment": "Pièce jointe", "image": "image", "document": "document"},
    "en": {"attachment": "Attachment", "image": "image", "document": "document"},
    "es": {"attachment": "Archivo adjunto", "image": "imagen", "document": "documento"},
    "de": {"attachment": "Anhang", "image": "Bild", "document": "Dokument"},
    "it": {"attachment": "Allegato", "image": "immagine", "document": "documento"},
    "zh": {"attachment": "附件", "image": "图片", "document": "文档"},
}


def build_attachment_hint(
    attachments: list[dict[str, Any]],
    user_language: str = "fr",
) -> str:
    """
    Build a lightweight text hint describing attached files.

    This hint is appended to the HumanMessage text so the Router,
    SemanticPivot, and Planner can correctly classify the user intent
    (e.g., vision analysis rather than a vague query).

    Args:
        attachments: List of attachment metadata dicts with keys:
            content_type, original_filename, mime_type.
        user_language: ISO 639-1 language code for labels.

    Returns:
        Human-readable hint string, e.g.:
        "[Pièce jointe : 1 image (photo.jpg), 1 document (facture.pdf)]"
    """
    labels = _HINT_LABELS.get(user_language, _HINT_LABELS["en"])

    parts: list[str] = []
    for att in attachments:
        cat = labels.get(att["content_type"], att["content_type"])
        parts.append(f"{cat} ({att['original_filename']})")

    count_text = ", ".join(parts)
    return f"{ATTACHMENT_HINT_MARKER}[{labels['attachment']} : {count_text}]"


def build_vision_message(
    text: str,
    attachments: list[dict[str, Any]],
    storage_path: str,
) -> HumanMessage:
    """
    Build a multimodal HumanMessage with base64-encoded images and PDF text.

    This is called ephemerally in response_node just before the LLM call.
    The resulting message is NOT stored in the LangGraph state (avoids
    checkpoint bloat).

    Args:
        text: Original user message text (without annotation hint).
        attachments: List of attachment metadata dicts with keys:
            id, mime_type, content_type, file_path, original_filename,
            extracted_text.
        storage_path: Base storage path (ATTACHMENTS_STORAGE_PATH).

    Returns:
        HumanMessage with content as list[dict] (multimodal format):
        [{"type": "text", ...}, {"type": "image_url", ...}, ...]
    """
    content: list[dict[str, Any]] = [{"type": "text", "text": text}]

    for att in attachments:
        if att["content_type"] == AttachmentContentType.IMAGE:
            _append_image_content(content, att, storage_path)
        elif att["content_type"] == AttachmentContentType.DOCUMENT:
            _append_document_content(content, att)

    return HumanMessage(content=content)  # type: ignore[arg-type]


def _append_image_content(
    content: list[dict[str, Any]],
    attachment: dict[str, Any],
    storage_path: str,
) -> None:
    """Load image from disk and append as base64 image_url block."""
    file_path = Path(storage_path) / attachment["file_path"]

    try:
        image_bytes = file_path.read_bytes()
        b64_data = base64.b64encode(image_bytes).decode("utf-8")
        mime_type = attachment["mime_type"]

        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{b64_data}",
                    "detail": "auto",
                },
            }
        )

        logger.debug(
            "vision_image_encoded",
            attachment_id=attachment["id"],
            size_bytes=len(image_bytes),
        )

    except FileNotFoundError:
        logger.warning(
            "vision_image_file_missing",
            attachment_id=attachment["id"],
            file_path=str(file_path),
        )
    except OSError as exc:
        logger.error(
            "vision_image_read_error",
            attachment_id=attachment["id"],
            file_path=str(file_path),
            error=str(exc),
        )


def _append_document_content(
    content: list[dict[str, Any]],
    attachment: dict[str, Any],
) -> None:
    """Append extracted PDF text as a text block."""
    extracted_text = attachment.get("extracted_text")
    if not extracted_text:
        logger.warning(
            "vision_document_no_text",
            attachment_id=attachment["id"],
            original_filename=attachment["original_filename"],
        )
        return

    content.append(
        {
            "type": "text",
            "text": (f"[Document: {attachment['original_filename']}]\n" f"{extracted_text}"),
        }
    )

    logger.debug(
        "vision_document_text_injected",
        attachment_id=attachment["id"],
        text_length=len(extracted_text),
    )
