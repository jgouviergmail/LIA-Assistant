"""Archive-first persistence of the user turn (ADR-117).

Extracted verbatim from ``AgentService._archive_user_message_first``
(file-size ratchet — a logical file never grows): the user message must be
persisted BEFORE graph execution so the turn survives client disconnects,
cancellations and crashes. End-of-run HITL flags are patched onto this row
during finalization by ``AgentService._patch_user_message_hitl_flags``.

Habits program Lot 0 addition: when the run is automated (scheduled action
executor), the archived row now carries ``is_automated_source: true`` in its
metadata. Without the marker, a synthetic user message is indistinguishable
from a human one at the message level (the conversation is 1:1 per user), and
the rhythm profile would learn from LIA's own automations — a feedback loop.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from src.domains.conversations.service import ConversationService

logger = structlog.get_logger(__name__)


async def archive_user_message_first(
    *,
    conv_service: ConversationService,
    conversation_id: uuid.UUID,
    user_message: str,
    run_id: str,
    is_hitl_resumption: bool,
    attachment_meta: dict[str, Any],
    stt_kwargs: dict[str, Any],
    is_automated_source: bool = False,
) -> uuid.UUID | None:
    """Persist the user message BEFORE graph execution (archive-first).

    ADR-117 (Lot 1): the user turn must survive client disconnects,
    cancellations and crashes. End-of-run HITL flags (decision_type,
    hitl_interrupted) are patched onto this row during finalization.

    Args:
        conv_service: Conversation service used for archiving.
        conversation_id: Target conversation UUID.
        user_message: Raw user message content.
        run_id: Run identifier stored in the row metadata.
        is_hitl_resumption: True when this message answers a pending
            HITL interrupt (sets ``hitl_response`` immediately).
        attachment_meta: Attachment metadata block ({} when none).
        stt_kwargs: Per-message STT cost attribution kwargs.
        is_automated_source: True when the run is automated (e.g. scheduled
            action) — stamps ``is_automated_source: true`` into the row
            metadata so batch consumers (habit rhythm profile) can exclude
            synthetic user messages. Never written when False: absence is
            the human default, mirroring the source-policy NULL semantics.

    Returns:
        The archived row id, or None when archiving failed (best-effort:
        an archiving hiccup must never block the generation itself).
    """
    from src.core.field_names import FIELD_IS_AUTOMATED_SOURCE, FIELD_RUN_ID
    from src.infrastructure.database import get_db_context

    metadata: dict[str, Any] = {FIELD_RUN_ID: run_id, **attachment_meta}
    if is_hitl_resumption:
        metadata["hitl_response"] = True
    if is_automated_source:
        metadata[FIELD_IS_AUTOMATED_SOURCE] = True
    try:
        async with get_db_context() as archive_db:
            row = await conv_service.archive_message(
                conversation_id,
                "user",
                user_message,
                metadata,
                archive_db,
                **stt_kwargs,
            )
            return row.id
    except Exception as archive_err:  # noqa: BLE001 — must not kill the run
        logger.error(
            "archive_first_user_message_failed",
            run_id=run_id,
            conversation_id=str(conversation_id),
            error=str(archive_err),
            error_type=type(archive_err).__name__,
        )
        return None
