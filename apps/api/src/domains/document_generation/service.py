"""Document generation service: LLM structured content -> rendered attachment (ADR-226).

Pipeline: dedicated ``document_generation`` LLM slot (structured output typed
per format family) -> pure renderer -> attachments storage (TTL purge) ->
pending store for SSE card delivery. Failures propagate to the TOOL layer,
which translates them into honest UnifiedToolOutput failures — this module
never fakes a success and never queues a card for a document that does not
exist on disk.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from src.core.config import settings
from src.core.constants import DOCUMENT_GENERATION_LLM_TYPE
from src.core.i18n_types import get_language_name
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.attachments.models import AttachmentContentType, AttachmentStatus
from src.domains.attachments.repository import AttachmentRepository
from src.domains.document_generation.document_store import (
    PendingDocument,
    store_pending_document,
)
from src.domains.document_generation.prompts import load_document_prompt
from src.domains.document_generation.renderers import (
    DOCUMENT_EXTENSIONS,
    DOCUMENT_MIME_TYPES,
    render_document,
)
from src.domains.document_generation.sanitize import sanitize_filename_stem
from src.domains.document_generation.schemas import (
    SCHEMA_BY_DOC_TYPE,
    DocumentContent,
    DocumentType,
)
from src.infrastructure.database.session import get_db_context
from src.infrastructure.llm.factory import get_llm
from src.infrastructure.llm.structured_output import get_structured_output_with_retry
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GeneratedDocumentResult:
    """Outcome of a successful document generation."""

    attachment_id: str
    url: str
    filename: str
    doc_type: str
    size_bytes: int
    expires_at_iso: str | None
    truncated_source: bool


async def _call_document_llm(
    *,
    doc_type: DocumentType,
    instructions: str,
    source_data: str,
    language: str,
    config: RunnableConfig | None,
) -> DocumentContent:
    """Produce structured document content with the dedicated LLM slot.

    Module-level seam (patched in unit tests). Mirrors
    ``telephony/return_synthesis.py``: get_llm + provider from the resolved
    config + retried structured output. Passing ``config`` through keeps the
    graph's token-tracking callbacks attached (node_name = the LLM type).

    Args:
        doc_type: Target format (selects the content schema BEFORE the call).
        instructions: What the document must contain.
        source_data: Raw material (already truncated by the caller).
        language: Backend-canonical language code for the document content.
        config: RunnableConfig carrying the run's callbacks, or ``None``.

    Returns:
        Validated content matching ``SCHEMA_BY_DOC_TYPE[doc_type]``.
    """
    system = load_document_prompt("document_generation_prompt", "v1").format(
        language=get_language_name(language),
        instructions=instructions,
        source_data=source_data,
    )
    # The literal satisfies the LLMType Literal; the constant (same value,
    # asserted by a test) feeds the str-typed config-helper lookup.
    llm = get_llm("document_generation")
    provider = get_llm_config_for_agent(settings, DOCUMENT_GENERATION_LLM_TYPE).provider
    return await get_structured_output_with_retry(
        llm=llm,
        messages=[
            SystemMessage(content=system),
            HumanMessage(content="Produce the document now."),
        ],
        schema=SCHEMA_BY_DOC_TYPE[doc_type],
        provider=provider,
        node_name=DOCUMENT_GENERATION_LLM_TYPE,
        config=config,
    )


async def _write_document_file(data: bytes, relative_path: str) -> None:
    """Persist rendered bytes under the attachments storage root (off-loop).

    Args:
        data: Rendered document bytes.
        relative_path: Path relative to ``attachments_storage_path``.
    """
    absolute_path = Path(settings.attachments_storage_path) / relative_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(absolute_path.write_bytes, data)


async def generate_document_for_user(
    *,
    user_id: uuid.UUID,
    conversation_id: str,
    doc_type: DocumentType,
    instructions: str,
    source_data: str,
    requested_filename: str,
    language: str,
    config: RunnableConfig | None,
) -> GeneratedDocumentResult:
    """Generate, render and store one document; queue its card for delivery.

    Args:
        user_id: Owner of the resulting attachment.
        conversation_id: Thread id the card is delivered to.
        doc_type: Target format.
        instructions: What the document must contain.
        source_data: Optional raw material (research results, prior steps).
        requested_filename: User-requested stem; wins over the LLM suggestion.
        language: Backend-canonical language code for the document content.
        config: RunnableConfig carrying the run's callbacks, or ``None``.

    Returns:
        The stored document's metadata.

    Raises:
        Exception: LLM/renderer/storage failures propagate — the TOOL layer
            translates them into honest UnifiedToolOutput failures.
    """
    cap = settings.document_generation_max_source_chars
    truncated = len(source_data) > cap
    content = await _call_document_llm(
        doc_type=doc_type,
        instructions=instructions,
        source_data=source_data[:cap],
        language=language,
        config=config,
    )

    data = await asyncio.to_thread(render_document, doc_type, content)

    stem = sanitize_filename_stem(requested_filename or content.filename_stem)
    extension = DOCUMENT_EXTENSIONS[doc_type]
    download_filename = f"{stem}.{extension}"
    stored_filename = f"{uuid.uuid4()}.{extension}"
    relative_path = f"{user_id}/{stored_filename}"
    await _write_document_file(data, relative_path)

    async with get_db_context() as db:
        repo = AttachmentRepository(db)
        attachment = await repo.create(
            {
                "user_id": user_id,
                "original_filename": download_filename,
                "stored_filename": stored_filename,
                "mime_type": DOCUMENT_MIME_TYPES[doc_type],
                "file_size": len(data),
                "file_path": relative_path,
                "content_type": AttachmentContentType.DOCUMENT,
                "status": AttachmentStatus.READY,
                "expires_at": datetime.now(UTC) + timedelta(hours=settings.attachments_ttl_hours),
            }
        )
        # Serialized next to its source (the image-tool convention): what
        # leaves this block is an ISO string, never a datetime.
        expires_at_iso = attachment.expires_at.isoformat() if attachment.expires_at else None
        await db.commit()
        attachment_id = str(attachment.id)

    url = f"/api/v1/attachments/{attachment_id}"
    store_pending_document(
        conversation_id,
        PendingDocument(
            url=url,
            filename=download_filename,
            doc_type=doc_type.value,
            size_bytes=len(data),
            expires_at=expires_at_iso,
        ),
    )
    logger.info(
        "document_generation_attachment_saved",
        attachment_id=attachment_id,
        user_id=str(user_id),
        doc_type=doc_type.value,
        file_size=len(data),
        truncated_source=truncated,
    )
    return GeneratedDocumentResult(
        attachment_id=attachment_id,
        url=url,
        filename=download_filename,
        doc_type=doc_type.value,
        size_bytes=len(data),
        expires_at_iso=expires_at_iso,
        truncated_source=truncated,
    )
