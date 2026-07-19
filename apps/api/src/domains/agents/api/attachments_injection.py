"""Attachment injection into the loaded LangGraph state (evolution F4).

Extracted from the streaming orchestrator (``service.py``) so the frozen
module stays under its size cap and the injection logic is testable in
isolation. Annotates the last HumanMessage with the attachment hint (Router/
Planner awareness) and stores lightweight metadata for response_node late
resolution.
"""

from __future__ import annotations

import uuid
from typing import Any

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


async def inject_attachments_into_state(
    *,
    state: Any,
    attachment_ids: list[uuid.UUID],
    user_id: uuid.UUID,
    user_language: str,
    run_id: str,
    db: Any,
) -> None:
    """Inject attachment hint + metadata into the loaded state (evolution F4).

    Annotates the last HumanMessage so Router/Planner see the attachments and
    stores lightweight metadata for response_node late resolution. Extracted
    from the streaming orchestrator (F011/F015 hotspot budget).
    """
    from src.domains.attachments.llm_content import build_attachment_hint
    from src.domains.attachments.service import AttachmentService

    attachment_service = AttachmentService(db)
    attachments = await attachment_service.get_batch(attachment_ids, user_id)
    if not attachments:
        return

    # Annotate last HumanMessage for Router/Planner awareness
    hint = build_attachment_hint(
        [
            {
                "content_type": a.content_type,
                "original_filename": a.original_filename,
                "mime_type": a.mime_type,
            }
            for a in attachments
        ],
        user_language=user_language,
    )
    from langchain_core.messages import HumanMessage

    for i in range(len(state["messages"]) - 1, -1, -1):
        if isinstance(state["messages"][i], HumanMessage):
            state["messages"][i] = HumanMessage(
                content=f"{state['messages'][i].content}\n\n{hint}",
                id=state["messages"][i].id,
            )
            break

    # Store lightweight metadata for response_node late resolution
    state["metadata"]["current_turn_attachments"] = [
        {
            "id": str(a.id),
            "mime_type": a.mime_type,
            "content_type": a.content_type,
            "file_path": a.file_path,
            "file_size": a.file_size,
            "original_filename": a.original_filename,
            "extracted_text": a.extracted_text,
        }
        for a in attachments
    ]

    logger.info(
        "attachments_injected_into_state",
        run_id=run_id,
        attachment_count=len(attachments),
        content_types=[a.content_type for a in attachments],
    )
