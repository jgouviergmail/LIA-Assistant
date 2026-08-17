"""LangChain tool for AI document generation (ADR-226).

Mirrors ``image_generation_tools.py``: runtime context extraction, global
flag, user opt-in, validated inputs, dedicated internal LLM (via
``DocumentGenerationService``), Attachment storage (TTL cleanup),
pending-store card delivery, honest failure semantics — a failure after the
paid LLM call returns an explicit error, never a phantom success.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Annotated

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import settings
from src.core.i18n import normalize_language
from src.domains.agents.constants import AGENT_DOCUMENT_GENERATION
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.tool_registry import registered_tool
from src.domains.agents.utils.rate_limiting import rate_limit
from src.domains.document_generation.schemas import DocumentType
from src.domains.document_generation.service import generate_document_for_user
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

if TYPE_CHECKING:
    from src.domains.users.models import User

logger = get_logger(__name__)


async def _load_user(user_id: uuid.UUID) -> User | None:
    """Load the user row (module-level seam for tests).

    Args:
        user_id: The authenticated user's id.

    Returns:
        The ``User`` row, or ``None`` when it does not exist.
    """
    from src.domains.users.models import User
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        return await db.get(User, user_id)


@registered_tool
@track_tool_metrics(
    tool_name="generate_document",
    agent_name=AGENT_DOCUMENT_GENERATION,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: settings.document_generation_rate_limit_calls,
    window_seconds=lambda: settings.document_generation_rate_limit_window,
    scope="user",
)
async def generate_document(
    instructions: str,
    doc_type: str,
    source_data: str = "",
    filename: str = "",
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Create a downloadable document (csv, xlsx, docx, pptx, pdf, md, txt).

    The document content is written by a dedicated AI writer from your
    instructions and the optional source data, then rendered to the requested
    format and displayed as a downloadable card below the assistant response.

    Args:
        instructions: What the document must contain — subject, structure,
            level of detail, audience. Be specific.
        doc_type: Target format. One of: csv, xlsx, docx, pptx, pdf, md, txt.
        source_data: Optional raw material (e.g. research results from an
            earlier step) the document must be grounded in.
        filename: Optional filename (without extension) requested by the user.
    """
    start_time = time.time()

    # --- 1. Extract runtime context ---
    configurable = runtime.config.get("configurable", {}) if runtime else {}
    user_id_raw = configurable.get("user_id")
    if not user_id_raw:
        logger.warning("document_generation_no_user_id", has_runtime=runtime is not None)
        return UnifiedToolOutput.failure(
            message="Could not identify user. Please try again.",
            error_code="AUTH_ERROR",
        )

    # --- 2. Check global feature flag ---
    if not settings.document_generation_enabled:
        return UnifiedToolOutput.failure(
            message="Document generation is currently disabled by the administrator.",
            error_code="TOOL_ERROR",
        )

    # --- 3. Validate doc_type (normalize the repairable, reject the rest) ---
    # " .PDF " and "pdf" are the same intent: mechanically repairable, so
    # repaired. An unknown format cannot be repaired without inventing intent
    # (ADR-184) — it stays an error, with the full enum published.
    try:
        parsed_type = DocumentType(doc_type.strip().lower().lstrip("."))
    except ValueError:
        valid = ", ".join(t.value for t in DocumentType)
        return UnifiedToolOutput.failure(
            message=f"Invalid doc_type '{doc_type}'. Must be one of: {valid}",
            error_code="TOOL_ERROR",
        )

    # --- 4. Load user (opt-in + language) ---
    from src.domains.agents.tools.runtime_helpers import parse_user_id

    user_id = parse_user_id(user_id_raw)
    try:
        user = await _load_user(user_id)
    except Exception as exc:
        logger.error("document_generation_user_load_error", error=str(exc), user_id=str(user_id))
        return UnifiedToolOutput.failure(
            message="Error loading user preferences. Please try again.",
            error_code="TOOL_ERROR",
        )
    if not user:
        return UnifiedToolOutput.failure(message="User not found.", error_code="TOOL_ERROR")
    if not user.document_generation_enabled:
        return UnifiedToolOutput.failure(
            message=(
                "Document generation is not enabled in your settings. "
                "Enable it in Settings > Features > Document Generation."
            ),
            error_code="TOOL_ERROR",
        )

    # --- 5. Generate via the service (LLM -> render -> attachment -> card) ---
    conversation_id = str(configurable.get("thread_id", "unknown"))
    try:
        result = await generate_document_for_user(
            user_id=user_id,
            conversation_id=conversation_id,
            doc_type=parsed_type,
            instructions=instructions,
            source_data=source_data,
            requested_filename=filename,
            language=normalize_language(user.language),
            config=runtime.config if runtime else None,
        )
    except Exception as exc:
        logger.error(
            "document_generation_failed",
            error_type=type(exc).__name__,
            error=str(exc),
            doc_type=parsed_type.value,
            user_id=str(user_id),
        )
        return UnifiedToolOutput.failure(
            message=(
                f"Document generation failed ({type(exc).__name__}). " "No document was produced."
            ),
            error_code="TOOL_ERROR",
        )

    # --- 6. Honest success ---
    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(
        "document_generation_tool_success",
        doc_type=result.doc_type,
        file_size=result.size_bytes,
        duration_ms=duration_ms,
        attachment_id=result.attachment_id,
    )
    truncation_note = (
        " Note: the provided source data exceeded the configured limit and was truncated."
        if result.truncated_source
        else ""
    )
    return UnifiedToolOutput.action_success(
        message=(
            f"Document '{result.filename}' generated successfully and displayed as a "
            f"downloadable card below the response.{truncation_note}\n"
            "Do NOT include any markdown link to the document — the card is already shown."
        ),
        structured_data={
            "document_url": result.url,
            "filename": result.filename,
            "doc_type": result.doc_type,
            "size_bytes": result.size_bytes,
        },
    )
