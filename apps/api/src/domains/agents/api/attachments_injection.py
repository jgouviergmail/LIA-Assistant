"""Attachment injection into the loaded LangGraph state (evolution F4).

Extracted from the streaming orchestrator (``service.py``) so the frozen
module stays under its size cap and the injection logic is testable in
isolation. Annotates the last HumanMessage with the attachment hint (Router/
Planner awareness) and stores lightweight metadata for response_node late
resolution.
"""

from __future__ import annotations

import uuid

import structlog
from langchain_core.messages import HumanMessage

from src.core.context import SkillTurnFile, record_skill_turn_files
from src.core.conversation_target import ConversationRef
from src.domains.agents.models import MessagesState
from src.domains.attachments.llm_content import build_attachment_hint
from src.domains.attachments.service import AttachmentService
from src.infrastructure.database import get_db_context

logger = structlog.get_logger(__name__)


def _annotate_last_human(state: MessagesState, hint: str) -> None:
    """Append the hint to the last HumanMessage, keeping everything else it carries.

    A copy, never a rebuild: its id, and the instant it was written (lot 17,
    ``message_view.WRITTEN_AT_KEY``), which every later turn reads with it.
    """
    messages = state["messages"]
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if isinstance(message, HumanMessage):
            messages[index] = message.model_copy(update={"content": f"{message.content}\n\n{hint}"})
            return


async def inject_attachments_into_state(
    *,
    state: MessagesState,
    attachment_ids: list[uuid.UUID],
    user_id: uuid.UUID,
    user_language: str,
    run_id: str,
    target: ConversationRef,
) -> None:
    """Inject attachment hint + metadata into the loaded state (evolution F4).

    Annotates the last HumanMessage so Router/Planner see the attachments and
    stores lightweight metadata for response_node late resolution. Extracted
    from the streaming orchestrator (F011/F015 hotspot budget).
    """
    # Accepted usage must survive even when the subsequent early archive fails.
    # This session closes before state projection or any model/provider work.
    async with get_db_context() as db:
        attachments = await AttachmentService(db).accept_for_conversation(
            attachment_ids, user_id, target
        )
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
    _annotate_last_human(state, hint)

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
    # A skill command carries them into its sandbox (ADR-327 lot 2).
    record_skill_turn_files(
        [
            SkillTurnFile(
                attachment_id=str(a.id),
                filename=a.original_filename,
                file_path=a.file_path,
                size=a.file_size,
            )
            for a in attachments
        ]
    )

    logger.info(
        "attachments_injected_into_state",
        run_id=run_id,
        attachment_count=len(attachments),
        content_types=[a.content_type for a in attachments],
    )
